import json

from fastapi.testclient import TestClient

from app.db.models import Message, SessionState, TurnSnapshot
from app.db.session import get_db
from app.main import create_app
from app.services.runtime.session_service import ensure_session_state


def make_client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def add_runtime_turn(db, session, sequence, trust_before, trust_after):
    message = Message(
        session_id=session.id,
        role="assistant",
        content=f"回复 {sequence}",
        sequence=sequence,
        generation_status="complete",
    )
    db.add(message)
    db.flush()
    snapshot = TurnSnapshot(
        session_id=session.id,
        message_id=message.id,
        state_before_json=json.dumps({"relationship": {"trust": trust_before}}),
        patch_json=json.dumps([
            {"op": "replace", "path": "/relationship/trust", "value": trust_after}
        ]),
        state_after_json=json.dumps({"relationship": {"trust": trust_after}}),
    )
    db.add(snapshot)
    db.flush()
    return message


def test_deleting_latest_runtime_message_restores_state_before(db_with_session):
    db, char, session = db_with_session
    runtime = ensure_session_state(db, session, char)
    runtime.state_json = json.dumps({"relationship": {"trust": 5}})
    message = add_runtime_turn(db, session, 2, trust_before=0, trust_after=5)
    db.commit()

    response = make_client(db).delete(f"/api/messages/{message.id}")

    assert response.status_code == 200
    db.refresh(runtime)
    assert json.loads(runtime.state_json)["relationship"]["trust"] == 0
    assert db.query(TurnSnapshot).filter_by(message_id=message.id).first() is None


def test_deleting_old_runtime_message_requires_rollback(db_with_session):
    db, char, session = db_with_session
    runtime = ensure_session_state(db, session, char)
    first = add_runtime_turn(db, session, 2, trust_before=0, trust_after=2)
    add_runtime_turn(db, session, 3, trust_before=2, trust_after=4)
    runtime.state_json = json.dumps({"relationship": {"trust": 4}})
    db.commit()

    response = make_client(db).delete(f"/api/messages/{first.id}")

    assert response.status_code == 409
    assert "回滚" in response.json()["detail"]
    assert db.query(Message).filter_by(id=first.id).first() is not None
