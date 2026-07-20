from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.models import Character, CharacterStateAlias, ChatSession, TurnSnapshot
from ..db.session import get_db
from ..schemas import CharacterStateAliasCreate, CharacterStateAliasRegistryResponse
from ..services.runtime.session_service import character_profile, json_load
from ..services.runtime.state_aliases import (
    build_alias_registry,
    normalize_alias_key,
    validate_alias_text,
)

router = APIRouter(prefix="/characters/{character_id}/state-aliases", tags=["state-aliases"])


def _character(db: Session, character_id: str) -> Character:
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    return character


def _operation_path(value: Any) -> str:
    if isinstance(value, dict):
        if isinstance(value.get("path"), str):
            return value["path"]
        operation = value.get("operation")
        if isinstance(operation, dict) and isinstance(operation.get("path"), str):
            return operation["path"]
    return ""


def _observed_unknown_paths(db: Session, character_id: str) -> list[str]:
    snapshots = (
        db.query(TurnSnapshot)
        .join(ChatSession, ChatSession.id == TurnSnapshot.session_id)
        .filter(ChatSession.character_id == character_id)
        .order_by(TurnSnapshot.created_at.desc())
        .limit(250)
        .all()
    )
    paths: list[str] = []
    seen: set[str] = set()
    for snapshot in snapshots:
        for item in json_load(snapshot.rejected_patch_json, []):
            path = _operation_path(item)
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
        for entry in json_load(snapshot.decision_trace_json, []):
            if not isinstance(entry, dict):
                continue
            field = entry.get("field")
            if not isinstance(field, dict) or field.get("classification") != "unresolved":
                continue
            path = str(field.get("path", ""))
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
    return paths[:100]


def _registry(db: Session, character: Character) -> dict[str, Any]:
    # character_profile overlays confirmed DB rows and keeps the same registry
    # representation used by the runtime.
    profile = character_profile(character, db)
    registry = profile.get("state_aliases", {}) if isinstance(profile, dict) else {}
    observed = _observed_unknown_paths(db, character.id)
    if observed:
        registry = build_alias_registry(
            profile.get("state_schema", {}),
            confirmed_rows=(
                db.query(CharacterStateAlias)
                .filter(CharacterStateAlias.character_id == character.id)
                .order_by(CharacterStateAlias.semantic.asc(), CharacterStateAlias.alias_key.asc())
                .all()
            ),
            observed_paths=observed,
            character_id=character.id,
        )
    return {**registry, "character_name": character.name}


@router.get("", response_model=CharacterStateAliasRegistryResponse)
def get_character_state_aliases(character_id: str, db: Session = Depends(get_db)):
    return _registry(db, _character(db, character_id))


@router.post("", response_model=CharacterStateAliasRegistryResponse)
def confirm_character_state_alias(
    character_id: str,
    payload: CharacterStateAliasCreate,
    db: Session = Depends(get_db),
):
    character = _character(db, character_id)
    try:
        alias = validate_alias_text(payload.alias)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    alias_key = normalize_alias_key(alias)

    base_profile = character_profile(character, db=None)
    schema = base_profile.get("state_schema", {}) if isinstance(base_profile, dict) else {}
    semantic_index = schema.get("semantic_index", {}) if isinstance(schema, dict) else {}
    target = semantic_index.get(payload.semantic) if isinstance(semantic_index, dict) else None
    canonical_path = str(target.get("canonical_path", "")) if isinstance(target, dict) else ""
    if not canonical_path:
        raise HTTPException(status_code=400, detail="当前角色卡没有该 semantic 的可写 Schema 目标")

    existing = (
        db.query(CharacterStateAlias)
        .filter(
            CharacterStateAlias.character_id == character.id,
            CharacterStateAlias.alias_key == alias_key,
        )
        .first()
    )
    if existing:
        existing.alias = alias
        existing.semantic = payload.semantic
        existing.canonical_path = canonical_path
        existing.source = "user_confirmed"
        existing.confidence = 1.0
    else:
        db.add(CharacterStateAlias(
            character_id=character.id,
            alias=alias,
            alias_key=alias_key,
            semantic=payload.semantic,
            canonical_path=canonical_path,
            source="user_confirmed",
            confidence=1.0,
        ))
    db.commit()
    return _registry(db, character)


@router.delete("/{alias_id}", response_model=CharacterStateAliasRegistryResponse)
def delete_character_state_alias(
    character_id: str,
    alias_id: str,
    db: Session = Depends(get_db),
):
    character = _character(db, character_id)
    row = (
        db.query(CharacterStateAlias)
        .filter(
            CharacterStateAlias.id == alias_id,
            CharacterStateAlias.character_id == character.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="角色卡别名不存在")
    db.delete(row)
    db.commit()
    return _registry(db, character)
