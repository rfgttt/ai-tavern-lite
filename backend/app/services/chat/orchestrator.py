from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any

from sqlalchemy.orm import Session

from ...core.logging import logger
from ...db.models import Message
from ...schemas import ChatRequest, PromptPreviewRequest, PromptPreviewResponse
from .context import PreparedChatStream
from .errors import ChatServiceError
from .helpers import touch_session
from .preparation import ChatPreparationService
from .stream_runner import ChatStreamRunner

ProviderFactory = Callable[..., object]


class ChatOrchestrator:
    """Facade for chat preparation, streaming, stopping, and prompt preview."""

    def __init__(
        self,
        db: Session,
        *,
        provider_factory: ProviderFactory,
        active_streams: MutableMapping[str, object],
        max_concurrent_generations: int,
    ) -> None:
        self.db = db
        self.active_streams = active_streams
        self.max_concurrent_generations = max_concurrent_generations
        self.preparation = ChatPreparationService(
            db,
            provider_factory=provider_factory,
        )
        self.runner = ChatStreamRunner(active_streams)

    def prepare_stream(self, request: ChatRequest) -> PreparedChatStream:
        if len(self.active_streams) >= self.max_concurrent_generations:
            raise ChatServiceError(
                429,
                "当前生成任务过多，请等待已有任务完成后重试",
                headers={"Retry-After": "3"},
            )

        context = self.preparation.prepare(request)
        self.active_streams[context.assistant_message_id] = context.provider
        logger.info(
            "Starting chat stream request_id=%s session=%s message=%s provider=%s model=%s mock=%s",
            context.request_id,
            context.session_id,
            context.assistant_message_id,
            context.app_settings.get("provider_name", "OpenAI Compatible"),
            context.app_settings.get("model", "") or "mock",
            bool(context.app_settings.get("mock_llm", True)),
        )
        return PreparedChatStream(
            events=self.runner.events(context),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Accel-Buffering": "no",
            },
        )

    def stop_generation(self, request: dict[str, Any]) -> dict[str, Any]:
        message_id = request.get("message_id")
        if not message_id:
            raise ChatServiceError(400, "缺少 message_id")

        provider = self.active_streams.get(message_id)
        message = self.db.query(Message).filter(Message.id == message_id).first()

        if provider is not None:
            cancel = getattr(provider, "cancel", None)
            if callable(cancel):
                cancel()
            if message:
                message.generation_status = "stopped"
                touch_session(message.session)
                self.db.commit()
            return {"success": True, "message": "已停止生成"}

        if message and message.generation_status == "generating":
            message.generation_status = "stopped"
            touch_session(message.session)
            self.db.commit()
            return {"success": True, "message": "已停止生成"}

        raise ChatServiceError(404, "未找到正在生成的消息")

    def prepare_regeneration(self, request: ChatRequest) -> ChatRequest:
        return self.preparation.prepare_regeneration(request)

    def preview_prompt(self, request: PromptPreviewRequest) -> PromptPreviewResponse:
        return self.preparation.preview_prompt(request)
