from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.models import Character, ChatSession, Message, SessionState, TurnSnapshot
from ..db.session import get_db
from ..schemas import (
    RuntimeRollbackRequest,
    RuntimeSessionResponse,
    RuntimeStateUpdate,
    TurnRuntimeResponse,
)
from ..services.runtime.session_service import (
    character_profile,
    ensure_session_state,
    json_load,
    runtime_payload,
    snapshot_payload,
)
from ..services.runtime.state_engine import serialize_state_document

router = APIRouter(tags=["runtime"])


def _get_session(db: Session, session_id: str) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.get("/characters/{character_id}/runtime-profile")
def get_character_runtime_profile(character_id: str, db: Session = Depends(get_db)):
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    return character_profile(character)


@router.get("/sessions/{session_id}/runtime", response_model=RuntimeSessionResponse)
def get_runtime(session_id: str, db: Session = Depends(get_db)):
    session = _get_session(db, session_id)
    runtime = ensure_session_state(db, session)
    db.commit()
    db.refresh(runtime)
    return runtime_payload(db, runtime)


@router.put("/sessions/{session_id}/runtime/state", response_model=RuntimeSessionResponse)
def replace_runtime_state(
    session_id: str,
    update: RuntimeStateUpdate,
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id)
    runtime = ensure_session_state(db, session)
    try:
        serialized = serialize_state_document(update.state)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    runtime.state_json = serialized
    runtime.revision = (runtime.revision or 0) + 1
    db.commit()
    db.refresh(runtime)
    return runtime_payload(db, runtime)


@router.get("/sessions/{session_id}/timeline", response_model=list[TurnRuntimeResponse])
def get_timeline(session_id: str, db: Session = Depends(get_db)):
    _get_session(db, session_id)
    snapshots = (
        db.query(TurnSnapshot)
        .join(Message, Message.id == TurnSnapshot.message_id)
        .filter(TurnSnapshot.session_id == session_id)
        .order_by(Message.sequence.asc())
        .all()
    )
    return [snapshot_payload(snapshot) for snapshot in snapshots]


@router.post("/sessions/{session_id}/rollback", response_model=RuntimeSessionResponse)
def rollback_session(
    session_id: str,
    request: RuntimeRollbackRequest,
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id)
    target = (
        db.query(Message)
        .filter(Message.id == request.message_id, Message.session_id == session_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="回滚目标消息不存在")

    runtime = ensure_session_state(db, session)
    retained_snapshot = (
        db.query(TurnSnapshot)
        .join(Message, Message.id == TurnSnapshot.message_id)
        .filter(
            TurnSnapshot.session_id == session_id,
            Message.sequence <= target.sequence,
        )
        .order_by(Message.sequence.desc())
        .first()
    )
    restore_state = (
        json_load(retained_snapshot.state_after_json, {})
        if retained_snapshot
        else json_load(runtime.initial_state_json, {})
    )

    later_messages = (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.sequence > target.sequence)
        .all()
    )
    later_ids = [message.id for message in later_messages]
    if later_ids:
        db.query(TurnSnapshot).filter(TurnSnapshot.message_id.in_(later_ids)).delete(
            synchronize_session=False
        )
        db.query(Message).filter(Message.id.in_(later_ids)).delete(synchronize_session=False)

    runtime.state_json = json.dumps(restore_state, ensure_ascii=False)
    runtime.revision = (runtime.revision or 0) + 1
    db.commit()
    db.refresh(runtime)
    return runtime_payload(db, runtime)
