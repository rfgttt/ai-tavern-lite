import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.models import Persona
from ..db.session import get_db
from ..schemas import PersonaCreate, PersonaUpdate

router = APIRouter(prefix="/personas", tags=["personas"])


def _payload(persona: Persona) -> dict:
    try:
        metadata = json.loads(persona.metadata_json or "{}")
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    return {
        "id": persona.id,
        "name": persona.name,
        "description": persona.description,
        "pronouns": persona.pronouns,
        "avatar_path": persona.avatar_path,
        "metadata": metadata,
        "is_default": bool(persona.is_default),
        "created_at": persona.created_at,
        "updated_at": persona.updated_at,
    }


@router.get("")
def list_personas(db: Session = Depends(get_db)):
    return [_payload(item) for item in db.query(Persona).order_by(Persona.updated_at.desc()).all()]


@router.post("")
def create_persona(data: PersonaCreate, db: Session = Depends(get_db)):
    if data.is_default:
        db.query(Persona).update({Persona.is_default: False})
    persona = Persona(
        name=data.name,
        description=data.description,
        pronouns=data.pronouns,
        avatar_path=data.avatar_path,
        metadata_json=json.dumps(data.metadata, ensure_ascii=False),
        is_default=data.is_default,
    )
    db.add(persona)
    db.commit()
    db.refresh(persona)
    return _payload(persona)


@router.put("/{persona_id}")
def update_persona(persona_id: str, data: PersonaUpdate, db: Session = Depends(get_db)):
    persona = db.query(Persona).filter(Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona 不存在")
    values = data.model_dump(exclude_unset=True)
    if values.get("is_default"):
        db.query(Persona).update({Persona.is_default: False})
    for key, value in values.items():
        if key == "metadata":
            persona.metadata_json = json.dumps(value or {}, ensure_ascii=False)
        else:
            setattr(persona, key, value)
    db.commit()
    db.refresh(persona)
    return _payload(persona)


@router.delete("/{persona_id}")
def delete_persona(persona_id: str, db: Session = Depends(get_db)):
    persona = db.query(Persona).filter(Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona 不存在")
    db.delete(persona)
    db.commit()
    return {"success": True}
