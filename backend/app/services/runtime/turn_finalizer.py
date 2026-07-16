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
from .session_service import ensure_session_state, snapshot_payload
from .state_engine import apply_patch


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
        applied_count = 0
        rejected_count = 0

        if final_status == "complete":
            patch_result = apply_patch(state_before, operations)
            state_after = patch_result.state
            runtime.state_json = _json(state_after)
            runtime.revision = (runtime.revision or 0) + 1
            snapshot = TurnSnapshot(
                session_id=session_id,
                message_id=message_id,
                state_before_json=_json(state_before),
                patch_json=_json(patch_result.applied),
                state_after_json=_json(state_after),
                events_json=_json(events),
                choices_json=_json(choices),
                dice_json=_json(dice),
                battle_checks_json=_json(battle_checks),
                battle_json=_json(battle),
                expression=expression,
                triggered_lorebook_json=_json(triggered_lorebook),
                rejected_patch_json=_json(patch_result.rejected),
                parser_errors_json=_json(parser_errors),
            )
            db.add(snapshot)
            db.flush()
            runtime_turn = snapshot_payload(snapshot)
            patch_applied = True
            applied_count = len(patch_result.applied)
            rejected_count = len(patch_result.rejected)
        else:
            state_after = state_before

        render_data = parse_message_ast(visible_content)
        artifacts: list[dict[str, Any]] = []
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

        message.content = visible_content
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
