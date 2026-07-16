import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.models import Character, CharacterGroup, GroupMember
from ..db.session import get_db
from ..schemas import GroupCreate

router = APIRouter(prefix="/groups", tags=["groups"])


def _payload(group: CharacterGroup) -> dict:
    try:
        metadata = json.loads(group.metadata_json or "{}")
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    members = sorted(group.members, key=lambda item: item.position)
    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "character_ids": [item.character_id for item in members],
        "members": [
            {
                "character_id": item.character_id,
                "name": item.character.name if item.character else "",
                "avatar_path": item.character.avatar_path if item.character else "",
                "role": item.role,
                "position": item.position,
            }
            for item in members
        ],
        "metadata": metadata,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
    }


def _replace_members(db: Session, group: CharacterGroup, character_ids: list[str]) -> None:
    deduped = list(dict.fromkeys(character_ids))
    existing = db.query(Character).filter(Character.id.in_(deduped)).all() if deduped else []
    if len(existing) != len(deduped):
        raise HTTPException(status_code=400, detail="包含不存在的角色")
    db.query(GroupMember).filter(GroupMember.group_id == group.id).delete(synchronize_session=False)
    for position, character_id in enumerate(deduped):
        db.add(GroupMember(group_id=group.id, character_id=character_id, position=position))


@router.get("")
def list_groups(db: Session = Depends(get_db)):
    return [_payload(item) for item in db.query(CharacterGroup).order_by(CharacterGroup.updated_at.desc()).all()]


@router.post("")
def create_group(data: GroupCreate, db: Session = Depends(get_db)):
    group = CharacterGroup(
        name=data.name,
        description=data.description,
        metadata_json=json.dumps(data.metadata, ensure_ascii=False),
    )
    db.add(group)
    db.flush()
    _replace_members(db, group, data.character_ids)
    db.commit()
    db.refresh(group)
    return _payload(group)


@router.put("/{group_id}")
def update_group(group_id: str, data: GroupCreate, db: Session = Depends(get_db)):
    group = db.query(CharacterGroup).filter(CharacterGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="群组不存在")
    group.name = data.name
    group.description = data.description
    group.metadata_json = json.dumps(data.metadata, ensure_ascii=False)
    _replace_members(db, group, data.character_ids)
    db.commit()
    db.refresh(group)
    return _payload(group)


@router.delete("/{group_id}")
def delete_group(group_id: str, db: Session = Depends(get_db)):
    group = db.query(CharacterGroup).filter(CharacterGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="群组不存在")
    db.delete(group)
    db.commit()
    return {"success": True}
