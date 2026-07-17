from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import sessionmaker

from ..prompt_builder.builder import BuiltPrompt


@dataclass(frozen=True)
class PreparedChatStream:
    events: AsyncIterator[str]
    media_type: str = "text/event-stream"
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class ChatStreamContext:
    request_id: str
    started_at: float
    started_wall_time: str
    session_id: str
    character_id: str
    character_name: str
    user_message_id: str | None
    assistant_message_id: str
    replacement_message_id: str | None
    user_message_payload: dict[str, Any] | None
    assistant_message_payload: dict[str, Any]
    session_factory: sessionmaker
    app_settings: dict[str, Any]
    query_text: str
    built_prompt: BuiltPrompt
    prompt_history_count: int
    triggered_lorebook_count: int
    memories_count: int
    lorebook_meta: list[dict[str, Any]]
    runtime_profile: dict[str, Any]
    state_before: dict[str, Any]
    runtime_revision_before: int
    provider: object
