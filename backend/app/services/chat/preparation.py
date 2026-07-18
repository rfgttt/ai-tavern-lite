from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from ...core.logging import logger
from ...db.models import Character, ChatSession, Message, TurnSnapshot
from ...schemas import ChatRequest, PromptPreviewRequest, PromptPreviewResponse, PromptSection
from ..lorebook.service import LorebookService
from ..memory.service import MemoryService
from ..prompt_builder.builder import PromptBuilder
from ..runtime.session_service import ensure_session_state, json_load
from ..settings_service import SettingsService
from .context import ChatStreamContext
from .errors import ChatServiceError
from .helpers import (
    last_user_content,
    lorebook_payload,
    message_payload,
    sanitize_error,
    session_identity_context,
    touch_session,
)

ProviderFactory = Callable[..., object]


class ChatPreparationService:
    """Load chat dependencies and prepare immutable stream context."""

    def __init__(
        self,
        db: Session,
        *,
        provider_factory: ProviderFactory,
    ) -> None:
        self.db = db
        self.provider_factory = provider_factory

    def prepare(self, request: ChatRequest) -> ChatStreamContext:
        session = self.require_session(request.session_id)
        character = self.require_character(session.character_id)
        replacement_message, replacement_snapshot = self._load_replacement(
            session,
            request.replacement_message_id,
        )

        app_settings = SettingsService.get_all_settings(self.db)
        # Validate provider configuration before writing any pending messages.
        provider = self._create_provider(app_settings, character.name)

        request_id = uuid4().hex[:12]
        started_at = perf_counter()
        started_wall_time = datetime.now(timezone.utc).isoformat()

        messages = (
            self.db.query(Message)
            .filter(Message.session_id == session.id)
            .order_by(Message.sequence.asc())
            .all()
        )
        next_sequence = messages[-1].sequence + 1 if messages else 0

        user_message: Message | None = None
        if request.message:
            user_message = Message(
                session_id=session.id,
                role="user",
                content=request.message,
                sequence=next_sequence,
                generation_status="complete",
            )
            self.db.add(user_message)
            self.db.flush()
            messages.append(user_message)
            next_sequence += 1

        assistant_message = Message(
            session_id=session.id,
            role="assistant",
            content="",
            sequence=next_sequence,
            generation_status="generating",
        )
        self.db.add(assistant_message)
        touch_session(session)
        self.db.commit()
        if user_message:
            self.db.refresh(user_message)
        self.db.refresh(assistant_message)

        session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.db.get_bind(),
        )

        recent_text = "\n".join(
            message.content for message in messages[-10:] if message.content
        )
        normalized = self._normalized_character(character)

        runtime = ensure_session_state(self.db, session, character)
        runtime_profile = json_load(runtime.profile_json, {})
        state_before = json_load(
            request.replacement_state_json
            or (replacement_snapshot.state_before_json if replacement_snapshot else None)
            or runtime.state_json,
            {},
        )
        runtime_revision_before = runtime.revision or 0
        # The stream uses an independent transaction after the response starts.
        self.db.commit()

        lorebook_entries = LorebookService.parse_entries(
            normalized.get("character_book", {})
        )
        triggered_lorebook = LorebookService.get_triggered_entries(
            lorebook_entries,
            recent_text,
        )
        query_text = request.message or last_user_content(messages)
        prompt_history = [
            message
            for message in messages
            if not replacement_message or message.id != replacement_message.id
        ]
        if (
            query_text
            and messages
            and messages[-1].role == "user"
            and messages[-1].content == query_text
        ):
            prompt_history = messages[:-1]

        memories = MemoryService.get_relevant_memories(
            self.db,
            character_id=character.id,
            session_id=session.id,
            query_text=query_text,
            max_entries=app_settings.get("max_memory_entries", 12),
        )
        persona_payload, group_characters = session_identity_context(
            self.db,
            session,
        )

        built_prompt = PromptBuilder(
            character=character,
            username=app_settings.get("username", "用户"),
            context_window=app_settings.get("context_window", 8192),
            max_new_tokens=app_settings.get("max_tokens", 1024),
        ).build(
            messages=prompt_history,
            lorebook_entries=triggered_lorebook,
            lorebook_catalog=lorebook_entries,
            memories=memories,
            user_message=query_text,
            runtime_profile=runtime_profile,
            runtime_state=state_before,
            persona=persona_payload,
            group_characters=group_characters,
        )

        return ChatStreamContext(
            request_id=request_id,
            started_at=started_at,
            started_wall_time=started_wall_time,
            session_id=session.id,
            character_id=character.id,
            character_name=character.name,
            user_message_id=user_message.id if user_message else None,
            assistant_message_id=assistant_message.id,
            replacement_message_id=(
                replacement_message.id if replacement_message else None
            ),
            user_message_payload=message_payload(user_message),
            assistant_message_payload=message_payload(assistant_message) or {},
            session_factory=session_factory,
            app_settings=app_settings,
            query_text=query_text,
            built_prompt=built_prompt,
            prompt_history_count=len(prompt_history),
            triggered_lorebook_count=len(triggered_lorebook),
            memories_count=len(memories),
            lorebook_meta=lorebook_payload(
                triggered_lorebook,
                set(built_prompt.selected_lorebook_ids),
            ),
            runtime_profile=runtime_profile,
            state_before=state_before,
            runtime_revision_before=runtime_revision_before,
            provider=provider,
        )

    def prepare_regeneration(self, request: ChatRequest) -> ChatRequest:
        session = self.require_session(request.session_id)
        last_assistant = (
            self.db.query(Message)
            .filter(
                Message.session_id == session.id,
                Message.role == "assistant",
            )
            .order_by(Message.sequence.desc())
            .first()
        )
        if not last_assistant:
            raise ChatServiceError(409, "当前会话没有可重新生成的助手回复")

        snapshot = (
            self.db.query(TurnSnapshot)
            .filter(TurnSnapshot.message_id == last_assistant.id)
            .first()
        )
        runtime = ensure_session_state(self.db, session)
        state_before_json = snapshot.state_before_json if snapshot else runtime.state_json

        return ChatRequest(
            session_id=request.session_id,
            message="",
            replacement_message_id=last_assistant.id,
            replacement_state_json=state_before_json,
        )

    def preview_prompt(self, request: PromptPreviewRequest) -> PromptPreviewResponse:
        session = self.require_session(request.session_id)
        character = self.require_character(session.character_id)
        app_settings = SettingsService.get_all_settings(self.db)
        messages = (
            self.db.query(Message)
            .filter(Message.session_id == session.id)
            .order_by(Message.sequence.asc())
            .all()
        )

        recent_text = "\n".join(
            message.content for message in messages[-10:] if message.content
        )
        if request.message:
            recent_text += "\n" + request.message

        normalized = self._normalized_character(character)
        lorebook_entries = LorebookService.parse_entries(
            normalized.get("character_book", {})
        )
        triggered_lorebook = LorebookService.get_triggered_entries(
            lorebook_entries,
            recent_text,
        )
        query_text = request.message or last_user_content(messages)
        memories = MemoryService.get_relevant_memories(
            self.db,
            character_id=character.id,
            session_id=session.id,
            query_text=query_text,
            max_entries=app_settings.get("max_memory_entries", 12),
        )
        runtime = ensure_session_state(self.db, session, character)
        runtime_profile = json_load(runtime.profile_json, {})
        runtime_state = json_load(runtime.state_json, {})
        persona_payload, group_characters = session_identity_context(
            self.db,
            session,
        )

        built_prompt = PromptBuilder(
            character=character,
            username=app_settings.get("username", "用户"),
            context_window=app_settings.get("context_window", 8192),
            max_new_tokens=app_settings.get("max_tokens", 1024),
        ).build(
            messages=messages,
            lorebook_entries=triggered_lorebook,
            lorebook_catalog=lorebook_entries,
            memories=memories,
            user_message=request.message,
            runtime_profile=runtime_profile,
            runtime_state=runtime_state,
            persona=persona_payload,
            group_characters=group_characters,
        )

        return PromptPreviewResponse(
            sections=[
                PromptSection(
                    name=section.name,
                    content=(
                        section.content[:500] + "..."
                        if len(section.content) > 500
                        else section.content
                    ),
                    estimated_tokens=section.estimated_tokens,
                    source=section.source,
                )
                for section in built_prompt.sections
            ],
            total_estimated_tokens=built_prompt.total_estimated_tokens,
            context_budget=built_prompt.context_budget,
        )

    def require_session(self, session_id: str) -> ChatSession:
        session = (
            self.db.query(ChatSession)
            .filter(ChatSession.id == session_id)
            .first()
        )
        if not session:
            raise ChatServiceError(404, "会话不存在")
        return session

    def require_character(self, character_id: str) -> Character:
        character = (
            self.db.query(Character)
            .filter(Character.id == character_id)
            .first()
        )
        if not character:
            raise ChatServiceError(404, "角色不存在")
        return character

    def _load_replacement(
        self,
        session: ChatSession,
        replacement_message_id: str | None,
    ) -> tuple[Message | None, TurnSnapshot | None]:
        if not replacement_message_id:
            return None, None

        replacement_message = (
            self.db.query(Message)
            .filter(
                Message.id == replacement_message_id,
                Message.session_id == session.id,
                Message.role == "assistant",
            )
            .first()
        )
        if not replacement_message:
            raise ChatServiceError(
                409,
                "要替换的旧回复已不存在，请刷新会话后重试。",
            )
        replacement_snapshot = (
            self.db.query(TurnSnapshot)
            .filter(TurnSnapshot.message_id == replacement_message.id)
            .first()
        )
        return replacement_message, replacement_snapshot

    def _create_provider(
        self,
        app_settings: dict[str, Any],
        character_name: str,
    ) -> object:
        secrets = [app_settings.get("api_key", "")]
        secrets.extend(
            value
            for value in (app_settings.get("custom_headers") or {}).values()
            if isinstance(value, str)
        )
        try:
            return self.provider_factory(
                mock_mode=app_settings.get("mock_llm", True),
                base_url=app_settings.get("base_url", ""),
                api_key=app_settings.get("api_key", ""),
                model=app_settings.get("model", ""),
                character_name=character_name,
            )
        except ValueError as error:
            raise ChatServiceError(
                422,
                sanitize_error(error, *secrets),
            ) from error
        except Exception as error:
            logger.error(
                "Chat provider initialization failed type=%s",
                error.__class__.__name__,
            )
            raise ChatServiceError(
                503,
                "模型服务初始化失败，请检查模型设置后重试",
            ) from error

    @staticmethod
    def _normalized_character(character: Character) -> dict[str, Any]:
        try:
            return (
                json.loads(character.normalized_json)
                if character.normalized_json
                else {}
            )
        except (json.JSONDecodeError, TypeError):
            return {}
