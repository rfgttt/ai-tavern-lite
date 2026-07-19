from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.config import settings as runtime_settings
from ..db.session import get_db
from ..schemas import ChatRequest, PromptPreviewRequest, PromptPreviewResponse
from ..services.chat import ChatOrchestrator, ChatServiceError
from ..services.chat.helpers import sanitize_error as _sanitize_error
from ..services.llm.provider import get_provider

router = APIRouter(tags=["chat"])

# Kept at the API boundary for stop requests and backwards-compatible tests.
_active_streams: dict[str, object] = {}
_active_sessions: dict[str, str] = {}


def _orchestrator(db: Session) -> ChatOrchestrator:
    return ChatOrchestrator(
        db,
        provider_factory=get_provider,
        active_streams=_active_streams,
        active_sessions=_active_sessions,
        max_concurrent_generations=runtime_settings.max_concurrent_generations,
    )


def _raise_http(error: ChatServiceError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail=error.detail,
        headers=error.headers,
    ) from error


@router.post("/chat/stream")
async def stream_chat(request: ChatRequest, db: Session = Depends(get_db)):
    """Save messages and stream a model response as structured SSE events."""
    try:
        prepared = _orchestrator(db).prepare_stream(request)
    except ChatServiceError as error:
        _raise_http(error)

    return StreamingResponse(
        prepared.events,
        media_type=prepared.media_type,
        headers=prepared.headers,
    )


@router.post("/chat/stop")
def stop_generation(request: dict[str, Any], db: Session = Depends(get_db)):
    """Stop a generating message."""
    try:
        return _orchestrator(db).stop_generation(request)
    except ChatServiceError as error:
        _raise_http(error)


@router.post("/chat/regenerate")
async def regenerate(request: ChatRequest, db: Session = Depends(get_db)):
    """Stream a replacement while preserving the last good reply until success."""
    try:
        regeneration_request = _orchestrator(db).prepare_regeneration(request)
    except ChatServiceError as error:
        _raise_http(error)
    return await stream_chat(regeneration_request, db)


@router.post("/chat/prompt-preview", response_model=PromptPreviewResponse)
def preview_prompt(
    request: PromptPreviewRequest,
    db: Session = Depends(get_db),
) -> PromptPreviewResponse:
    """Preview the prompt that would be sent to the model."""
    try:
        return _orchestrator(db).preview_prompt(request)
    except ChatServiceError as error:
        _raise_http(error)
