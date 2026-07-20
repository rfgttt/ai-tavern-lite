from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, MutableMapping
from time import perf_counter
from typing import Any

from ...core.logging import logger
from ...db.models import Message
from ..diagnostics.service import diagnostic_service
from ..memory.service import MemoryService
from ..runtime.output_parser import parse_runtime_output
from ..runtime.stream_filter import RuntimeStreamFilter
from ..runtime.state_recovery import recover_missing_state_update, should_attempt_recovery
from ..runtime.turn_finalizer import finalize_stream_turn
from .context import ChatStreamContext
from .helpers import sanitize_error, sse


class ChatStreamRunner:
    """Run one provider stream and persist the final durable turn."""

    def __init__(
        self,
        active_streams: MutableMapping[str, object],
        active_sessions: MutableMapping[str, str],
    ) -> None:
        self.active_streams = active_streams
        self.active_sessions = active_sessions

    async def events(self, context: ChatStreamContext) -> AsyncIterator[str]:
        raw_content = ""
        stream_filter = RuntimeStreamFilter()
        final_status = "generating"
        error_message: str | None = None
        error_type = ""
        chunk_count = 0
        first_token_ms: int | None = None
        closed_early = False

        try:
            try:
                yield sse(
                    {
                        "type": "runtime",
                        "request_id": context.request_id,
                        "session_id": context.session_id,
                        "profile": context.runtime_profile,
                        "state": context.state_before,
                        "revision": context.runtime_revision_before,
                        "triggered_lorebook": context.lorebook_meta,
                    }
                )
                yield sse(
                    {
                        "type": "message",
                        "request_id": context.request_id,
                        "user_message": context.user_message_payload,
                        "assistant_message": context.assistant_message_payload,
                    }
                )

                async for chunk in context.provider.chat_completion(
                    messages=context.built_prompt.messages,
                    temperature=context.app_settings.get("temperature", 0.7),
                    top_p=context.app_settings.get("top_p", 0.9),
                    max_tokens=context.app_settings.get("max_tokens", 1024),
                    stream=True,
                    custom_headers=context.app_settings.get("custom_headers"),
                ):
                    chunk_count += 1
                    if first_token_ms is None:
                        first_token_ms = round(
                            (perf_counter() - context.started_at) * 1000
                        )
                    raw_content += chunk
                    visible_chunk = stream_filter.feed(chunk)
                    if visible_chunk:
                        yield sse(
                            {
                                "type": "content",
                                "request_id": context.request_id,
                                "content": visible_chunk,
                                "message_id": context.assistant_message_id,
                            }
                        )

                trailing = stream_filter.finish()
                if trailing:
                    yield sse(
                        {
                            "type": "content",
                            "request_id": context.request_id,
                            "content": trailing,
                            "message_id": context.assistant_message_id,
                        }
                    )
                final_status = (
                    "stopped"
                    if bool(getattr(context.provider, "cancelled", False))
                    else "complete"
                )
            except asyncio.CancelledError:
                final_status = "stopped"
                error_type = "CancelledError"
                logger.info(
                    "Chat stream disconnected or stopped request_id=%s message=%s",
                    context.request_id,
                    context.assistant_message_id,
                )
            except GeneratorExit:
                final_status = "stopped"
                error_type = "GeneratorExit"
                closed_early = True
                logger.info(
                    "Chat stream closed before completion request_id=%s message=%s",
                    context.request_id,
                    context.assistant_message_id,
                )
            except Exception as error:
                final_status = "error"
                error_type = error.__class__.__name__
                error_message = self._sanitize_stream_error(context, error)
                logger.error(
                    "Chat stream error request_id=%s type=%s message=%s",
                    context.request_id,
                    error_type,
                    error_message,
                )
            finally:
                if final_status == "generating":
                    final_status = "stopped"

                parsed = parse_runtime_output(raw_content)
                primary_patch_operations = list(parsed.patch)
                operations = self._runtime_operations(parsed, final_status)
                state_update_source = (
                    "primary_response"
                    if primary_patch_operations
                    else ("primary_metadata" if operations else "none")
                )
                fallback_attempted = False
                fallback_reason = ""
                fallback_response_characters = 0
                fallback_http_completed = False
                fallback_finish_reason = ""
                fallback_response_type = ""
                fallback_error_type = ""
                fallback_reasoning_characters = 0
                fallback_reasoning_tokens = 0
                fallback_completion_tokens = 0
                fallback_requested_max_tokens = 0
                fallback_request_profile = ""
                should_recover, fallback_reason = should_attempt_recovery(
                    profile=context.runtime_profile,
                    enabled=bool(context.app_settings.get("auto_state_update_recovery", True)),
                    final_status=final_status,
                    primary_operations=primary_patch_operations,
                    provider_cancelled=bool(getattr(context.provider, "cancelled", False)),
                )
                if should_recover:
                    fallback_attempted = True
                    try:
                        recovery_provider = context.provider_factory(
                            mock_mode=context.app_settings.get("mock_llm", True),
                            base_url=context.app_settings.get("base_url", ""),
                            api_key=context.app_settings.get("api_key", ""),
                            model=context.app_settings.get("model", ""),
                            character_name=context.character_name,
                        )
                        self.active_streams[context.assistant_message_id] = recovery_provider
                        recovery = await recover_missing_state_update(
                            provider=recovery_provider,
                            state_before=context.state_before,
                            user_message=context.query_text,
                            assistant_narrative=parsed.narrative,
                            card_rules=context.state_update_rules,
                            custom_headers=context.app_settings.get("custom_headers"),
                        )
                        fallback_attempted = recovery.attempted
                        fallback_reason = recovery.reason
                        fallback_response_characters = recovery.response_characters
                        fallback_http_completed = recovery.http_completed
                        fallback_finish_reason = recovery.finish_reason
                        fallback_response_type = recovery.response_type
                        fallback_error_type = recovery.error_type
                        fallback_reasoning_characters = recovery.reasoning_characters
                        fallback_reasoning_tokens = recovery.reasoning_tokens
                        fallback_completion_tokens = recovery.completion_tokens
                        fallback_requested_max_tokens = recovery.requested_max_tokens
                        fallback_request_profile = recovery.request_profile
                        parsed.errors.extend(recovery.errors)
                        for event in recovery.events:
                            if event not in parsed.events:
                                parsed.events.append(event)
                        if recovery.operations:
                            operations.extend(recovery.operations)
                            state_update_source = "fallback_extractor"
                    except Exception as error:
                        fallback_reason = "fallback_provider_init_error"
                        fallback_error_type = error.__class__.__name__
                        parsed.errors.append(f"状态提取提供商初始化失败: {error.__class__.__name__}")

                final_result = finalize_stream_turn(
                    context.session_factory,
                    session_id=context.session_id,
                    message_id=context.assistant_message_id,
                    final_status=final_status,
                    visible_content=parsed.narrative,
                    state_before=context.state_before,
                    operations=operations,
                    events=parsed.events,
                    choices=parsed.choices,
                    dice=parsed.dice,
                    battle_checks=parsed.battle_checks,
                    battle=parsed.battle,
                    expression=parsed.expression,
                    triggered_lorebook=context.lorebook_meta,
                    parser_errors=parsed.errors,
                    state_update_source=state_update_source,
                    fallback_attempted=fallback_attempted,
                    fallback_reason=fallback_reason,
                    fallback_response_characters=fallback_response_characters,
                    fallback_http_completed=fallback_http_completed,
                    fallback_finish_reason=fallback_finish_reason,
                    fallback_response_type=fallback_response_type,
                    fallback_error_type=fallback_error_type,
                    fallback_reasoning_characters=fallback_reasoning_characters,
                    fallback_reasoning_tokens=fallback_reasoning_tokens,
                    fallback_completion_tokens=fallback_completion_tokens,
                    fallback_requested_max_tokens=fallback_requested_max_tokens,
                    fallback_request_profile=fallback_request_profile,
                )
                self._finalize_replacement(context, final_status)
                self._record_diagnostics(
                    context,
                    final_result=final_result,
                    final_status=final_status,
                    error_type=error_type,
                    error_message=error_message,
                    chunk_count=chunk_count,
                    first_token_ms=first_token_ms,
                    parser_error_count=len(parsed.errors),
                )

            if closed_early:
                return

            if error_message:
                yield sse(
                    {
                        "type": "error",
                        "request_id": context.request_id,
                        "message": error_message,
                        "message_id": context.assistant_message_id,
                    }
                )
            elif (
                final_status == "complete"
                and context.app_settings.get("auto_memory_extraction", False)
            ):
                self._extract_memories(context, final_result["content"])

            yield sse(
                {
                    "type": "done",
                    "request_id": context.request_id,
                    "message_id": context.assistant_message_id,
                    "status": final_status,
                    "content": final_result["content"],
                    "runtime": final_result["runtime"],
                    "state": final_result["state"],
                    "revision": final_result["revision"],
                    "segments": final_result["segments"],
                    "artifacts": final_result["artifacts"],
                    "speaker_metadata": final_result["speaker_metadata"],
                    "render_version": final_result["render_version"],
                }
            )
            yield "data: [DONE]\n\n"
        finally:
            self.active_streams.pop(context.assistant_message_id, None)
            if self.active_sessions.get(context.session_id) == context.assistant_message_id:
                self.active_sessions.pop(context.session_id, None)

    @staticmethod
    def _runtime_operations(parsed: Any, final_status: str) -> list[dict[str, Any]]:
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
        return operations

    @staticmethod
    def _finalize_replacement(
        context: ChatStreamContext,
        final_status: str,
    ) -> None:
        if not context.replacement_message_id:
            return

        with context.session_factory() as replacement_db:
            durable_new = (
                replacement_db.query(Message)
                .filter(Message.id == context.assistant_message_id)
                .first()
            )
            durable_old = (
                replacement_db.query(Message)
                .filter(Message.id == context.replacement_message_id)
                .first()
            )
            if final_status == "complete" and durable_new and durable_old:
                old_sequence = durable_old.sequence
                replacement_db.delete(durable_old)
                replacement_db.flush()
                durable_new.sequence = old_sequence
                replacement_db.commit()
            elif durable_new:
                # Failed/stopped regeneration must preserve the last good reply.
                replacement_db.delete(durable_new)
                replacement_db.commit()

    @staticmethod
    def _record_diagnostics(
        context: ChatStreamContext,
        *,
        final_result: dict[str, Any],
        final_status: str,
        error_type: str,
        error_message: str | None,
        chunk_count: int,
        first_token_ms: int | None,
        parser_error_count: int,
    ) -> None:
        retained_history = 0
        for section in context.built_prompt.sections:
            if section.name == "聊天历史":
                try:
                    retained_history = int(section.content.split()[0])
                except (ValueError, IndexError):
                    retained_history = 0
                break

        total_ms = round((perf_counter() - context.started_at) * 1000)
        diagnostic_service.record_chat_request(
            {
                "request_id": context.request_id,
                "started_at": context.started_wall_time,
                "session_id": context.session_id,
                "character_id": context.character_id,
                "user_message_id": context.user_message_id,
                "assistant_message_id": context.assistant_message_id,
                "provider": context.app_settings.get(
                    "provider_name", "OpenAI Compatible"
                ),
                "model": context.app_settings.get("model", "") or "mock",
                "mock_mode": bool(context.app_settings.get("mock_llm", True)),
                "timing": {
                    "first_token_ms": first_token_ms,
                    "total_ms": total_ms,
                },
                "prompt": {
                    "message_count": len(context.built_prompt.messages),
                    "estimated_tokens": context.built_prompt.total_estimated_tokens,
                    "context_budget": context.built_prompt.context_budget,
                    "worldbook_entries": context.triggered_lorebook_count,
                    "worldbook_titles": [
                        item["title"] for item in context.lorebook_meta[:20]
                    ],
                    "memories_injected": context.memories_count,
                    "history_messages": context.prompt_history_count,
                    "history_trimmed": max(
                        0,
                        context.prompt_history_count - retained_history,
                    ),
                },
                "generation": {
                    "chunks": chunk_count,
                    "visible_characters": len(final_result["content"]),
                    "finish_reason": final_status,
                    "stopped_by_user": final_status == "stopped",
                },
                "state": {
                    "version_before": context.runtime_revision_before,
                    "version_after": final_result["revision"],
                    "patch_applied": final_result["patch_applied"],
                    "state_changed": final_result["state_changed"],
                    "state_update_source": final_result["state_update_source"],
                    "fallback_attempted": final_result["fallback_attempted"],
                    "fallback_reason": final_result["fallback_reason"],
                    "fallback_response_characters": final_result["fallback_response_characters"],
                    "fallback_http_completed": final_result["fallback_http_completed"],
                    "fallback_finish_reason": final_result["fallback_finish_reason"],
                    "fallback_response_type": final_result["fallback_response_type"],
                    "fallback_error_type": final_result["fallback_error_type"],
                    "fallback_reasoning_characters": final_result["fallback_reasoning_characters"],
                    "fallback_reasoning_tokens": final_result["fallback_reasoning_tokens"],
                    "fallback_completion_tokens": final_result["fallback_completion_tokens"],
                    "fallback_requested_max_tokens": final_result["fallback_requested_max_tokens"],
                    "fallback_request_profile": final_result["fallback_request_profile"],
                    "applied_operations": final_result["applied_patch_count"],
                    "rejected_operations": final_result[
                        "rejected_patch_count"
                    ],
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

    @staticmethod
    def _extract_memories(
        context: ChatStreamContext,
        assistant_content: str,
    ) -> None:
        try:
            with context.session_factory() as memory_db:
                for memory_data in MemoryService.extract_memories_simple(
                    context.query_text,
                    assistant_content,
                ):
                    category = MemoryService.normalize_category(memory_data["category"])
                    MemoryService.add_memory(
                        memory_db,
                        content=memory_data["content"],
                        category=category,
                        importance=memory_data["importance"],
                        keywords=memory_data.get("keywords", ""),
                        character_id=context.character_id,
                        session_id=context.session_id,
                        skip_duplicate=(
                            category in MemoryService.AUTO_DEDUPE_CATEGORIES
                        ),
                    )
        except Exception as error:
            logger.warning(
                "Auto memory extraction failed: %s",
                sanitize_error(error),
            )

    @staticmethod
    def _sanitize_stream_error(
        context: ChatStreamContext,
        error: BaseException,
    ) -> str:
        header_secrets = [
            value
            for value in (context.app_settings.get("custom_headers") or {}).values()
            if isinstance(value, str)
        ]
        return sanitize_error(
            error,
            context.app_settings.get("api_key", ""),
            *header_secrets,
        )
