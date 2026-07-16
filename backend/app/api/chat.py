from datetime import datetime, timezone
import asyncio
import json
from time import perf_counter
from typing import Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from ..core.logging import logger
from ..core.config import settings as runtime_settings
from ..db.models import Character, ChatSession, Memory, Message, TurnSnapshot, Persona, CharacterGroup, GroupMember
from ..db.session import get_db
from ..schemas import ChatRequest, PromptPreviewRequest, PromptPreviewResponse, PromptSection
from ..services.llm.provider import get_provider
from ..services.lorebook.service import LorebookService
from ..services.memory.service import MemoryService
from ..services.prompt_builder.builder import PromptBuilder
from ..services.settings_service import SettingsService
from ..services.diagnostics.service import diagnostic_service
from ..services.runtime.output_parser import parse_runtime_output
from ..services.runtime.session_service import ensure_session_state, json_load, snapshot_payload
from ..services.runtime.state_engine import apply_patch
from ..services.runtime.stream_filter import RuntimeStreamFilter
from ..services.runtime.turn_finalizer import finalize_stream_turn
from ..services.rendering.message_ast import parse_message_ast

router = APIRouter(tags=["chat"])

# Active providers keyed by assistant message id. The stop endpoint calls cancel().
_active_streams: Dict[str, object] = {}


def _touch_session(session: ChatSession) -> None:
    session.updated_at = datetime.now()


def _safe_json_value(raw: str | None, fallback):
    try:
        return json.loads(raw) if raw else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


def _message_payload(message: Optional[Message]) -> Optional[dict]:
    if message is None:
        return None
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "sequence": message.sequence,
        "generation_status": message.generation_status,
        "segments": _safe_json_value(getattr(message, "segments_json", "[]"), []),
        "artifacts": _safe_json_value(getattr(message, "artifacts_json", "[]"), []),
        "speaker_metadata": _safe_json_value(getattr(message, "speaker_metadata_json", "{}"), {}),
        "render_version": getattr(message, "render_version", 2) or 2,
        "created_at": message.created_at.isoformat() if message.created_at else datetime.now().isoformat(),
        "updated_at": message.updated_at.isoformat() if message.updated_at else datetime.now().isoformat(),
    }


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sanitize_error(error: Exception, *secrets: str) -> str:
    message = str(error) or error.__class__.__name__
    for secret in secrets:
        if secret and secret in message:
            message = message.replace(secret, "***")
    return message


def _last_user_content(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content:
            return message.content
    return ""


def _lorebook_payload(entries: list, injected_ids: set | None = None) -> list[dict]:
    injected_ids = injected_ids if injected_ids is not None else {entry.id for entry in entries}
    return [
        {
            "id": entry.id,
            "title": entry.comment or f"条目 #{entry.id}",
            "keys": list(entry.keys)[:12],
            "position": entry.position,
            "content_preview": entry.content.strip()[:240],
            "trigger_type": "constant" if entry.constant else ("regex" if entry.use_regex else "keyword"),
            "injected": entry.id in injected_ids,
        }
        for entry in entries
    ]


def _session_identity_context(db: Session, session: ChatSession) -> tuple[dict | None, list[Character]]:
    persona_payload = None
    if getattr(session, "persona_id", None):
        persona = db.query(Persona).filter(Persona.id == session.persona_id).first()
        if persona:
            persona_payload = {
                "name": persona.name,
                "description": persona.description,
                "pronouns": persona.pronouns,
            }
    group_characters: list[Character] = []
    if getattr(session, "group_id", None):
        members = (
            db.query(GroupMember)
            .filter(GroupMember.group_id == session.group_id)
            .order_by(GroupMember.position.asc())
            .all()
        )
        group_characters = [member.character for member in members if member.character]
    return persona_payload, group_characters


@router.post("/chat/stream")
async def stream_chat(request: ChatRequest, db: Session = Depends(get_db)):
    """Save messages and stream a model response as structured SSE events."""
    if len(_active_streams) >= runtime_settings.max_concurrent_generations:
        raise HTTPException(
            status_code=429,
            detail="当前生成任务过多，请等待已有任务完成后重试",
            headers={"Retry-After": "3"},
        )

    session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    character = db.query(Character).filter(Character.id == session.character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")

    replacement_message = None
    replacement_snapshot = None
    if request.replacement_message_id:
        replacement_message = db.query(Message).filter(
            Message.id == request.replacement_message_id,
            Message.session_id == session.id,
            Message.role == "assistant",
        ).first()
        if not replacement_message:
            raise HTTPException(status_code=409, detail="要替换的旧回复已不存在，请刷新会话后重试。")
        replacement_snapshot = db.query(TurnSnapshot).filter(
            TurnSnapshot.message_id == replacement_message.id
        ).first()

    request_id = uuid4().hex[:12]
    started_at = perf_counter()
    started_wall_time = datetime.now(timezone.utc).isoformat()

    app_settings = SettingsService.get_all_settings(db)
    username = app_settings.get("username", "用户")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.sequence.asc())
        .all()
    )
    next_seq = messages[-1].sequence + 1 if messages else 0

    user_msg: Optional[Message] = None
    if request.message:
        user_msg = Message(
            session_id=session.id,
            role="user",
            content=request.message,
            sequence=next_seq,
            generation_status="complete",
        )
        db.add(user_msg)
        db.flush()
        messages.append(user_msg)
        next_seq += 1

    ai_msg = Message(
        session_id=session.id,
        role="assistant",
        content="",
        sequence=next_seq,
        generation_status="generating",
    )
    db.add(ai_msg)
    _touch_session(session)
    db.commit()
    if user_msg:
        db.refresh(user_msg)
    db.refresh(ai_msg)
    stream_session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db.get_bind(),
    )

    # The current user message is already in messages. PromptBuilder de-duplicates
    # it when user_message is also supplied, which keeps preview and stream aligned.
    recent_text = "\n".join(message.content for message in messages[-10:] if message.content)
    try:
        normalized = json.loads(character.normalized_json) if character.normalized_json else {}
    except (json.JSONDecodeError, TypeError):
        normalized = {}

    runtime = ensure_session_state(db, session, character)
    runtime_profile = json_load(runtime.profile_json, {})
    state_before = json_load(
        request.replacement_state_json
        or (replacement_snapshot.state_before_json if replacement_snapshot else None)
        or runtime.state_json,
        {},
    )
    runtime_revision_before = runtime.revision or 0
    # Persist the runtime row before returning StreamingResponse so the
    # independent stream transaction never races an uncommitted request write.
    db.commit()

    lorebook_entries = LorebookService.parse_entries(normalized.get("character_book", {}))
    triggered_lorebook = LorebookService.get_triggered_entries(lorebook_entries, recent_text)
    query_text = request.message or _last_user_content(messages)
    prompt_history = [
        message for message in messages
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
        db,
        character_id=character.id,
        query_text=query_text,
        max_entries=app_settings.get("max_memory_entries", 12),
    )

    persona_payload, group_characters = _session_identity_context(db, session)

    prompt_builder = PromptBuilder(
        character=character,
        username=username,
        context_window=app_settings.get("context_window", 8192),
        max_new_tokens=app_settings.get("max_tokens", 1024),
    )
    built_prompt = prompt_builder.build(
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

    provider = get_provider(
        mock_mode=app_settings.get("mock_llm", True),
        base_url=app_settings.get("base_url", ""),
        api_key=app_settings.get("api_key", ""),
        model=app_settings.get("model", ""),
        character_name=character.name,
    )
    _active_streams[ai_msg.id] = provider
    logger.info(
        "Starting chat stream request_id=%s session=%s message=%s provider=%s model=%s mock=%s",
        request_id,
        session.id,
        ai_msg.id,
        app_settings.get("provider_name", "OpenAI Compatible"),
        app_settings.get("model", "") or "mock",
        bool(app_settings.get("mock_llm", True)),
    )

    async def generate():
        raw_content = ""
        streamed_visible = ""
        stream_filter = RuntimeStreamFilter()
        final_status = "generating"
        error_message: Optional[str] = None
        runtime_turn: Optional[dict] = None
        lorebook_meta = _lorebook_payload(triggered_lorebook, set(built_prompt.selected_lorebook_ids))
        chunk_count = 0
        first_token_ms: Optional[int] = None
        patch_applied = False
        applied_patch_count = 0
        rejected_patch_count = 0
        parser_error_count = 0
        error_type = ""

        yield _sse(
            {
                "type": "runtime",
                "request_id": request_id,
                "session_id": session.id,
                "profile": runtime_profile,
                "state": state_before,
                "revision": runtime_revision_before,
                "triggered_lorebook": lorebook_meta,
            }
        )
        yield _sse(
            {
                "type": "message",
                "request_id": request_id,
                "user_message": _message_payload(user_msg),
                "assistant_message": _message_payload(ai_msg),
            }
        )

        try:
            async for chunk in provider.chat_completion(
                messages=built_prompt.messages,
                temperature=app_settings.get("temperature", 0.7),
                top_p=app_settings.get("top_p", 0.9),
                max_tokens=app_settings.get("max_tokens", 1024),
                stream=True,
                custom_headers=app_settings.get("custom_headers"),
            ):
                chunk_count += 1
                if first_token_ms is None:
                    first_token_ms = round((perf_counter() - started_at) * 1000)
                raw_content += chunk
                visible_chunk = stream_filter.feed(chunk)
                if visible_chunk:
                    streamed_visible += visible_chunk
                    yield _sse(
                        {
                            "type": "content",
                            "request_id": request_id,
                            "content": visible_chunk,
                            "message_id": ai_msg.id,
                        }
                    )

            trailing = stream_filter.finish()
            if trailing:
                streamed_visible += trailing
                yield _sse(
                    {
                        "type": "content",
                        "request_id": request_id,
                        "content": trailing,
                        "message_id": ai_msg.id,
                    }
                )
            final_status = "stopped" if bool(getattr(provider, "cancelled", False)) else "complete"
        except asyncio.CancelledError:
            final_status = "stopped"
            error_type = "CancelledError"
            logger.info("Chat stream disconnected or stopped request_id=%s message=%s", request_id, ai_msg.id)
        except Exception as error:
            final_status = "error"
            error_type = error.__class__.__name__
            header_secrets = [
                value
                for value in (app_settings.get("custom_headers") or {}).values()
                if isinstance(value, str)
            ]
            error_message = _sanitize_error(
                error,
                app_settings.get("api_key", ""),
                *header_secrets,
            )
            logger.error("Chat stream error request_id=%s type=%s message=%s", request_id, error_type, error_message)
        finally:
            parsed = parse_runtime_output(raw_content)
            parser_error_count = len(parsed.errors)
            visible_content = parsed.narrative

            operations = list(parsed.patch) if final_status == "complete" else []
            if final_status == "complete" and parsed.expression:
                operations.extend(
                    [
                        {
                            "op": "replace",
                            "path": "/character/expression",
                            "value": parsed.expression,
                        },
                        {
                            "op": "replace",
                            "path": "/character/mood",
                            "value": parsed.expression,
                        },
                    ]
                )
            if final_status == "complete" and parsed.battle is not None:
                operations.append(
                    {"op": "replace", "path": "/combat", "value": parsed.battle}
                )

            # Do not reuse the request-scoped Session here. FastAPI < 0.118
            # closes yield dependencies before a StreamingResponse is consumed.
            final_result = finalize_stream_turn(
                stream_session_factory,
                session_id=session.id,
                message_id=ai_msg.id,
                final_status=final_status,
                visible_content=visible_content,
                state_before=state_before,
                operations=operations,
                events=parsed.events,
                choices=parsed.choices,
                dice=parsed.dice,
                battle_checks=parsed.battle_checks,
                battle=parsed.battle,
                expression=parsed.expression,
                triggered_lorebook=lorebook_meta,
                parser_errors=parsed.errors,
            )

            if replacement_message:
                with stream_session_factory() as replacement_db:
                    durable_new = replacement_db.query(Message).filter(Message.id == ai_msg.id).first()
                    durable_old = replacement_db.query(Message).filter(Message.id == replacement_message.id).first()
                    if final_status == "complete" and durable_new and durable_old:
                        old_sequence = durable_old.sequence
                        replacement_db.delete(durable_old)
                        replacement_db.flush()
                        durable_new.sequence = old_sequence
                        replacement_db.commit()
                    elif durable_new:
                        # A failed/stopped regeneration must not destroy the last good reply.
                        replacement_db.delete(durable_new)
                        replacement_db.commit()

            runtime_turn = final_result["runtime"]
            state_after = final_result["state"]
            persisted_revision = final_result["revision"]
            render_data = {
                "segments": final_result["segments"],
                "speaker_metadata": final_result["speaker_metadata"],
            }
            artifacts = final_result["artifacts"]
            patch_applied = final_result["patch_applied"]
            applied_patch_count = final_result["applied_patch_count"]
            rejected_patch_count = final_result["rejected_patch_count"]
            _active_streams.pop(ai_msg.id, None)

            retained_history = 0
            for section in built_prompt.sections:
                if section.name == "聊天历史":
                    try:
                        retained_history = int(section.content.split()[0])
                    except (ValueError, IndexError):
                        retained_history = 0
                    break
            total_ms = round((perf_counter() - started_at) * 1000)
            diagnostic_service.record_chat_request(
                {
                    "request_id": request_id,
                    "started_at": started_wall_time,
                    "session_id": session.id,
                    "character_id": character.id,
                    "user_message_id": user_msg.id if user_msg else None,
                    "assistant_message_id": ai_msg.id,
                    "provider": app_settings.get("provider_name", "OpenAI Compatible"),
                    "model": app_settings.get("model", "") or "mock",
                    "mock_mode": bool(app_settings.get("mock_llm", True)),
                    "timing": {
                        "first_token_ms": first_token_ms,
                        "total_ms": total_ms,
                    },
                    "prompt": {
                        "message_count": len(built_prompt.messages),
                        "estimated_tokens": built_prompt.total_estimated_tokens,
                        "context_budget": built_prompt.context_budget,
                        "worldbook_entries": len(triggered_lorebook),
                        "worldbook_titles": [item["title"] for item in lorebook_meta[:20]],
                        "memories_injected": len(memories),
                        "history_messages": len(prompt_history),
                        "history_trimmed": max(0, len(prompt_history) - retained_history),
                    },
                    "generation": {
                        "chunks": chunk_count,
                        "visible_characters": len(visible_content),
                        "finish_reason": final_status,
                        "stopped_by_user": final_status == "stopped",
                    },
                    "state": {
                        "version_before": runtime_revision_before,
                        "version_after": persisted_revision,
                        "patch_applied": patch_applied,
                        "applied_operations": applied_patch_count,
                        "rejected_operations": rejected_patch_count,
                        "parser_errors": parser_error_count,
                    },
                    "error": (
                        {"type": error_type or "Error", "message": error_message}
                        if error_message
                        else None
                    ),
                    "status": final_status,
                }
            )

        if error_message:
            yield _sse({"type": "error", "request_id": request_id, "message": error_message, "message_id": ai_msg.id})
        elif final_status == "complete" and app_settings.get("auto_memory_extraction", False):
            try:
                with stream_session_factory() as memory_db:
                    for memory_data in MemoryService.extract_memories_simple(query_text, final_result["content"]):
                        MemoryService.add_memory(
                            memory_db,
                            content=memory_data["content"],
                            category=memory_data["category"],
                            importance=memory_data["importance"],
                            keywords=memory_data.get("keywords", ""),
                            character_id=character.id,
                            session_id=session.id,
                        )
            except Exception as error:
                logger.warning(f"Auto memory extraction failed: {_sanitize_error(error)}")

        yield _sse(
            {
                "type": "done",
                "request_id": request_id,
                "message_id": ai_msg.id,
                "status": final_status,
                "content": final_result["content"],
                "runtime": runtime_turn,
                "state": state_after,
                "revision": persisted_revision,
                "segments": render_data["segments"],
                "artifacts": artifacts,
                "speaker_metadata": render_data["speaker_metadata"],
                "render_version": final_result["render_version"],
            }
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/stop")
def stop_generation(request: dict, db: Session = Depends(get_db)):
    """Stop a generating message."""
    message_id = request.get("message_id")
    if not message_id:
        raise HTTPException(status_code=400, detail="缺少 message_id")

    provider = _active_streams.get(message_id)
    message = db.query(Message).filter(Message.id == message_id).first()

    if provider is not None:
        cancel = getattr(provider, "cancel", None)
        if callable(cancel):
            cancel()
        if message:
            message.generation_status = "stopped"
            _touch_session(message.session)
            db.commit()
        return {"success": True, "message": "已停止生成"}

    if message and message.generation_status == "generating":
        message.generation_status = "stopped"
        _touch_session(message.session)
        db.commit()
        return {"success": True, "message": "已停止生成"}

    raise HTTPException(status_code=404, detail="未找到正在生成的消息")


@router.post("/chat/regenerate")
async def regenerate(request: ChatRequest, db: Session = Depends(get_db)):
    """Stream a replacement while preserving the last good reply until success."""
    session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    last_assistant = (
        db.query(Message)
        .filter(Message.session_id == session.id, Message.role == "assistant")
        .order_by(Message.sequence.desc())
        .first()
    )
    if not last_assistant:
        raise HTTPException(status_code=409, detail="当前会话没有可重新生成的助手回复")

    snapshot = db.query(TurnSnapshot).filter(TurnSnapshot.message_id == last_assistant.id).first()
    runtime = ensure_session_state(db, session)
    state_before_json = snapshot.state_before_json if snapshot else runtime.state_json

    return await stream_chat(
        ChatRequest(
            session_id=request.session_id,
            message="",
            replacement_message_id=last_assistant.id,
            replacement_state_json=state_before_json,
        ),
        db,
    )


@router.post("/chat/prompt-preview", response_model=PromptPreviewResponse)
def preview_prompt(request: PromptPreviewRequest, db: Session = Depends(get_db)):
    """Preview the prompt that would be sent to the model."""
    session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    character = db.query(Character).filter(Character.id == session.character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")

    app_settings = SettingsService.get_all_settings(db)
    messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.sequence.asc())
        .all()
    )

    recent_text = "\n".join(message.content for message in messages[-10:] if message.content)
    if request.message:
        recent_text += "\n" + request.message

    try:
        normalized = json.loads(character.normalized_json) if character.normalized_json else {}
    except (json.JSONDecodeError, TypeError):
        normalized = {}

    lorebook_entries = LorebookService.parse_entries(normalized.get("character_book", {}))
    triggered_lorebook = LorebookService.get_triggered_entries(lorebook_entries, recent_text)
    query_text = request.message or _last_user_content(messages)
    memories = MemoryService.get_relevant_memories(
        db,
        character_id=character.id,
        query_text=query_text,
        max_entries=app_settings.get("max_memory_entries", 12),
    )
    runtime = ensure_session_state(db, session, character)
    runtime_profile = json_load(runtime.profile_json, {})
    runtime_state = json_load(runtime.state_json, {})
    persona_payload, group_characters = _session_identity_context(db, session)

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
                content=section.content[:500] + "..." if len(section.content) > 500 else section.content,
                estimated_tokens=section.estimated_tokens,
                source=section.source,
            )
            for section in built_prompt.sections
        ],
        total_estimated_tokens=built_prompt.total_estimated_tokens,
        context_budget=built_prompt.context_budget,
    )
