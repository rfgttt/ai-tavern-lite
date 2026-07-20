import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.models import ChatSession, Message, SessionBranch, TurnSnapshot
from ..db.session import get_db
from ..schemas import BranchCreate
from ..services.runtime.session_service import ensure_session_state, snapshot_payload

router = APIRouter(tags=["branches"])


def _branch_payload(branch: SessionBranch) -> dict:
    try:
        messages = json.loads(branch.messages_json or "[]")
    except (json.JSONDecodeError, TypeError):
        messages = []
    return {
        "id": branch.id,
        "session_id": branch.session_id,
        "title": branch.title,
        "parent_message_id": branch.parent_message_id or "",
        "message_count": len(messages),
        "runtime_revision": branch.runtime_revision or 0,
        "created_at": branch.created_at,
    }


def _serialize_message(message: Message) -> dict:
    snapshot = snapshot_payload(message.turn_snapshot) if message.turn_snapshot else None
    if snapshot:
        snapshot.pop("id", None)
        snapshot.pop("message_id", None)
        snapshot.pop("created_at", None)
    return {
        "role": message.role,
        "content": message.content,
        "sequence": message.sequence,
        "generation_status": message.generation_status,
        "segments_json": getattr(message, "segments_json", "[]") or "[]",
        "artifacts_json": getattr(message, "artifacts_json", "[]") or "[]",
        "speaker_metadata_json": getattr(message, "speaker_metadata_json", "{}") or "{}",
        "render_version": getattr(message, "render_version", 2) or 2,
        "turn_snapshot": snapshot,
    }


def _restore_snapshot(db: Session, session_id: str, message_id: str, payload: dict | None) -> None:
    if not isinstance(payload, dict):
        return
    db.add(TurnSnapshot(
        session_id=session_id,
        message_id=message_id,
        state_before_json=json.dumps(payload.get("state_before", {}), ensure_ascii=False),
        patch_json=json.dumps(payload.get("patch", []), ensure_ascii=False),
        state_after_json=json.dumps(payload.get("state_after", {}), ensure_ascii=False),
        events_json=json.dumps(payload.get("events", []), ensure_ascii=False),
        choices_json=json.dumps(payload.get("choices", []), ensure_ascii=False),
        dice_json=json.dumps(payload.get("dice", []), ensure_ascii=False),
        battle_checks_json=json.dumps(payload.get("battle_checks", []), ensure_ascii=False),
        battle_json=json.dumps(payload.get("battle"), ensure_ascii=False),
        expression=str(payload.get("expression") or ""),
        triggered_lorebook_json=json.dumps(payload.get("triggered_lorebook", []), ensure_ascii=False),
        rejected_patch_json=json.dumps(payload.get("rejected_patch", []), ensure_ascii=False),
        parser_errors_json=json.dumps(payload.get("parser_errors", []), ensure_ascii=False),
        decision_trace_json=json.dumps(payload.get("decision_trace", []), ensure_ascii=False),
    ))


@router.get("/sessions/{session_id}/branches")
def list_branches(session_id: str, db: Session = Depends(get_db)):
    return [
        _branch_payload(item)
        for item in db.query(SessionBranch).filter(SessionBranch.session_id == session_id).order_by(SessionBranch.created_at.desc()).all()
    ]


@router.post("/sessions/{session_id}/branches")
def save_branch(session_id: str, data: BranchCreate, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    query = db.query(Message).filter(Message.session_id == session_id)
    if data.parent_message_id:
        parent = db.query(Message).filter(Message.id == data.parent_message_id, Message.session_id == session_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="分支锚点不存在")
        query = query.filter(Message.sequence <= parent.sequence)
    messages = query.order_by(Message.sequence.asc()).all()
    runtime = ensure_session_state(db, session)

    branch_state_json = runtime.state_json or "{}"
    branch_revision = runtime.revision or 0
    if data.parent_message_id:
        parent_snapshot = (
            db.query(TurnSnapshot)
            .filter(
                TurnSnapshot.session_id == session_id,
                TurnSnapshot.message_id == data.parent_message_id,
            )
            .first()
        )
        if parent_snapshot is not None:
            branch_state_json = parent_snapshot.state_after_json or "{}"
            branch_revision = parent.sequence + 1
        else:
            # User/system messages do not always own a snapshot. Use the latest
            # durable assistant snapshot at or before the selected anchor.
            snapshot_row = (
                db.query(TurnSnapshot, Message)
                .join(Message, Message.id == TurnSnapshot.message_id)
                .filter(
                    TurnSnapshot.session_id == session_id,
                    Message.sequence <= parent.sequence,
                )
                .order_by(Message.sequence.desc())
                .first()
            )
            if snapshot_row is not None:
                snapshot, snapshot_message = snapshot_row
                branch_state_json = snapshot.state_after_json or "{}"
                branch_revision = snapshot_message.sequence + 1
            else:
                branch_state_json = runtime.initial_state_json or "{}"
                branch_revision = 0

    branch = SessionBranch(
        session_id=session_id,
        title=data.title,
        parent_message_id=data.parent_message_id or (messages[-1].id if messages else ""),
        messages_json=json.dumps([_serialize_message(item) for item in messages], ensure_ascii=False),
        runtime_state_json=branch_state_json,
        runtime_revision=branch_revision,
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return _branch_payload(branch)


@router.post("/sessions/{session_id}/branches/{branch_id}/restore")
def restore_branch(session_id: str, branch_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    branch = db.query(SessionBranch).filter(SessionBranch.id == branch_id, SessionBranch.session_id == session_id).first()
    if not session or not branch:
        raise HTTPException(status_code=404, detail="分支不存在")
    try:
        messages = json.loads(branch.messages_json or "[]")
    except (json.JSONDecodeError, TypeError):
        messages = []
    db.query(TurnSnapshot).filter(TurnSnapshot.session_id == session_id).delete(synchronize_session=False)
    db.query(Message).filter(Message.session_id == session_id).delete(synchronize_session=False)
    for index, item in enumerate(messages):
        restored_message = Message(
            session_id=session_id,
            role=item.get("role", "assistant"),
            content=item.get("content", ""),
            sequence=index,
            generation_status=item.get("generation_status", "complete"),
            segments_json=item.get("segments_json", "[]"),
            artifacts_json=item.get("artifacts_json", "[]"),
            speaker_metadata_json=item.get("speaker_metadata_json", "{}"),
            render_version=item.get("render_version", 2),
        )
        db.add(restored_message)
        db.flush()
        _restore_snapshot(db, session_id, restored_message.id, item.get("turn_snapshot"))
    runtime = ensure_session_state(db, session)
    runtime.state_json = branch.runtime_state_json or "{}"
    runtime.revision = (runtime.revision or 0) + 1
    db.commit()
    return {"success": True, "branch": _branch_payload(branch), "restored_messages": len(messages)}


@router.delete("/sessions/{session_id}/branches/{branch_id}")
def delete_branch(session_id: str, branch_id: str, db: Session = Depends(get_db)):
    branch = db.query(SessionBranch).filter(SessionBranch.id == branch_id, SessionBranch.session_id == session_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="分支不存在")
    db.delete(branch)
    db.commit()
    return {"success": True}
