"""Persist the final state of a streamed chat turn in an independent transaction.

FastAPI versions before 0.118 close yield dependencies before a StreamingResponse
body is consumed. A request-scoped SQLAlchemy Session must therefore never be
used by the stream generator after the endpoint returns the response.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from ...db.models import ChatSession, Message, TurnSnapshot
from ..rendering.message_ast import parse_message_ast
from .decision_trace import build_decision_trace
from .session_service import ensure_session_state, json_load, snapshot_payload
from .state_engine import apply_patch
from .state_aliases import normalize_alias_operations
from .state_policy import apply_stage_projection, enforce_state_policy
from .state_schema import reconcile_state_schema


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def finalize_stream_turn(
    session_factory: Callable[[], Session],
    *,
    session_id: str,
    message_id: str,
    final_status: str,
    visible_content: str,
    state_before: dict[str, Any],
    operations: list[dict[str, Any]],
    events: list[Any],
    choices: list[Any],
    dice: list[Any],
    battle_checks: list[Any],
    battle: Any,
    expression: str,
    triggered_lorebook: list[dict[str, Any]],
    parser_errors: list[Any],
    state_update_source: str = "none",
    fallback_attempted: bool = False,
    fallback_reason: str = "",
    fallback_response_characters: int = 0,
    fallback_http_completed: bool = False,
    fallback_finish_reason: str = "",
    fallback_response_type: str = "",
    fallback_error_type: str = "",
    fallback_reasoning_characters: int = 0,
    fallback_reasoning_tokens: int = 0,
    fallback_completion_tokens: int = 0,
    fallback_requested_max_tokens: int = 0,
    fallback_request_profile: str = "",
) -> dict[str, Any]:
    """Finalize one assistant turn and return the persisted response payload."""

    with session_factory() as db:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        message = db.query(Message).filter(Message.id == message_id, Message.session_id == session_id).first()
        if not session or not message:
            raise RuntimeError("流式回复对应的会话或消息不存在")

        runtime = ensure_session_state(db, session)
        runtime_turn: dict[str, Any] | None = None
        patch_applied = False
        state_changed = False
        applied_count = 0
        rejected_count = 0

        if final_status == "complete":
            previous_snapshots = (
                db.query(TurnSnapshot)
                .filter(TurnSnapshot.session_id == session_id)
                .all()
            )
            runtime_profile = json_load(runtime.profile_json, {})
            state_policy = runtime_profile.get("state_policy", {}) if isinstance(runtime_profile, dict) else {}
            state_schema = reconcile_state_schema(
                runtime_profile.get("state_schema", {}) if isinstance(runtime_profile, dict) else {},
                state_before,
            )
            alias_registry = runtime_profile.get("state_aliases", {}) if isinstance(runtime_profile, dict) else {}
            alias_result = normalize_alias_operations(operations, state_schema, alias_registry)
            policy_result = enforce_state_policy(
                state_before,
                alias_result.operations,
                state_policy,
                previous_snapshots,
            )
            patch_result = apply_patch(
                state_before,
                policy_result.operations,
                schema=state_schema,
                aliases=alias_registry,
            )
            engine_rejected = list(patch_result.rejected)
            patch_result.rejected = [*policy_result.rejected, *engine_rejected]
            policy_events = [
                f"状态规则调整：{item.get('reason', '按角色卡规则调整操作')}"
                for item in policy_result.adjusted
            ]
            persisted_events = [*events, *policy_events]
            state_after = apply_stage_projection(patch_result.state, state_policy)
            decision_trace = build_decision_trace(
                source=state_update_source,
                raw_operations=operations,
                alias_operations=alias_result.operations,
                alias_events=alias_result.events,
                policy_operations=policy_result.operations,
                adjusted=policy_result.adjusted,
                schema_adjusted=patch_result.adjusted,
                policy_rejected=policy_result.rejected,
                applied=patch_result.applied,
                engine_rejected=engine_rejected,
                state_before=state_before,
                state_after=state_after,
                state_schema=state_schema,
            )
            current_state = json_load(runtime.state_json, {})
            state_changed = state_after != current_state
            if state_changed:
                runtime.state_json = _json(state_after)
                runtime.revision = (runtime.revision or 0) + 1
            snapshot = TurnSnapshot(
                session_id=session_id,
                message_id=message_id,
                state_before_json=_json(state_before),
                patch_json=_json(patch_result.applied),
                state_after_json=_json(state_after),
                events_json=_json(persisted_events),
                choices_json=_json(choices),
                dice_json=_json(dice),
                battle_checks_json=_json(battle_checks),
                battle_json=_json(battle),
                expression=expression,
                triggered_lorebook_json=_json(triggered_lorebook),
                rejected_patch_json=_json(patch_result.rejected),
                parser_errors_json=_json(parser_errors),
                decision_trace_json=_json(decision_trace),
            )
            db.add(snapshot)
            db.flush()
            runtime_turn = snapshot_payload(snapshot)
            applied_count = len(patch_result.applied)
            patch_applied = applied_count > 0
            rejected_count = len(patch_result.rejected)
        else:
            state_after = state_before

        render_data = parse_message_ast(visible_content)
        artifacts: list[dict[str, Any]] = list(render_data.get("artifacts", []))
        if runtime_turn:
            artifacts.extend({"type": "dice", "data": item} for item in runtime_turn.get("dice", []))
            artifacts.extend(
                {"type": "battle-check", "data": item}
                for item in runtime_turn.get("battle_checks", [])
            )
            if runtime_turn.get("battle"):
                artifacts.append({"type": "battle-map", "data": runtime_turn["battle"]})
            if runtime_turn.get("patch"):
                artifacts.append({"type": "state-diff", "data": runtime_turn["patch"]})

        message.content = str(render_data.get("content", visible_content))
        message.generation_status = final_status
        message.segments_json = _json(render_data["segments"])
        message.speaker_metadata_json = _json(render_data["speaker_metadata"])
        message.artifacts_json = _json(artifacts)
        message.render_version = 2
        session.updated_at = datetime.now()
        db.commit()

        # Re-read after commit so the SSE done event reflects durable state.
        persisted_runtime = ensure_session_state(db, session)
        db.refresh(message)

        return {
            "message_id": message.id,
            "content": message.content,
            "status": message.generation_status,
            "runtime": runtime_turn,
            "state": state_after,
            "revision": persisted_runtime.revision or 0,
            "segments": render_data["segments"],
            "artifacts": artifacts,
            "speaker_metadata": render_data["speaker_metadata"],
            "render_version": 2,
            "patch_applied": patch_applied,
            "state_changed": state_changed,
            "state_update_source": state_update_source if patch_applied else "none",
            "fallback_attempted": fallback_attempted,
            "fallback_reason": fallback_reason,
            "fallback_response_characters": fallback_response_characters,
            "fallback_http_completed": fallback_http_completed,
            "fallback_finish_reason": fallback_finish_reason,
            "fallback_response_type": fallback_response_type,
            "fallback_error_type": fallback_error_type,
            "fallback_reasoning_characters": fallback_reasoning_characters,
            "fallback_reasoning_tokens": fallback_reasoning_tokens,
            "fallback_completion_tokens": fallback_completion_tokens,
            "fallback_requested_max_tokens": fallback_requested_max_tokens,
            "fallback_request_profile": fallback_request_profile,
            "applied_patch_count": applied_count,
            "rejected_patch_count": rejected_count,
        }


def recover_interrupted_generations(session_factory: Callable[[], Session]) -> int:
    """Mark leftover generating messages as stopped when the app starts."""

    with session_factory() as db:
        messages = (
            db.query(Message)
            .filter(Message.generation_status == "generating")
            .all()
        )
        for message in messages:
            message.generation_status = "stopped"
        if messages:
            db.commit()
        return len(messages)
