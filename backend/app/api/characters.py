from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
from typing import List
import json
import os
from pathlib import Path
import uuid

from ..db.session import get_db
from ..db.models import Character, ChatSession, Message, Memory
from ..schemas import (
    CharacterResponse, CharacterUpdate, CharacterCreate,
    Lorebook, LorebookEntry
)
from ..services.character_parser.parser import (
    parse_json_character, parse_png_character, export_character_v3
)
from ..core.config import settings
from ..core.logging import logger

router = APIRouter(prefix="/characters", tags=["characters"])

MAX_UPLOAD_SIZE = settings.max_upload_size_mb * 1024 * 1024


async def _read_upload_limited(file: UploadFile, max_size: int = MAX_UPLOAD_SIZE) -> bytes:
    """Read at most max_size + 1 bytes so oversized uploads are rejected early."""
    chunks: list[bytes] = []
    total = 0
    while True:
        remaining_probe = max_size - total + 1
        chunk = await file.read(min(1024 * 1024, remaining_probe))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"文件过大，最大允许 {settings.max_upload_size_mb}MB",
            )
    return b"".join(chunks)


@router.get("", response_model=List[CharacterResponse])
def list_characters(db: Session = Depends(get_db)):
    """List all characters."""
    characters = db.query(Character).order_by(Character.created_at.desc()).all()
    return characters


@router.post("/import", response_model=CharacterResponse)
async def import_character(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Import a character card (JSON or PNG)."""
    content = await _read_upload_limited(file)

    filename = file.filename or ""
    filename_lower = filename.lower()

    try:
        if filename_lower.endswith(".json"):
            # JSON character card
            try:
                json_data = json.loads(content.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise HTTPException(status_code=400, detail=f"JSON 解析失败: {e}")

            normalized, raw_data = parse_json_character(json_data)
            avatar_path = ""

        elif filename_lower.endswith(".png"):
            # PNG character card
            try:
                normalized, raw_data, avatar_bytes = parse_png_character(content)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            # Save avatar
            avatar_id = str(uuid.uuid4())
            avatar_filename = f"{avatar_id}.png"
            avatar_path_full = settings.avatars_dir / avatar_filename
            with open(avatar_path_full, "wb") as f:
                f.write(avatar_bytes)
            avatar_path = f"/avatars/{avatar_filename}"

        else:
            raise HTTPException(
                status_code=400,
                detail="不支持的文件格式，请上传 .json 或 .png 角色卡文件"
            )

        # Create character in DB
        character = Character(
            name=normalized.name or "未知角色",
            description=normalized.description,
            personality=normalized.personality,
            scenario=normalized.scenario,
            first_message=normalized.first_mes,
            normalized_json=json.dumps(normalized.to_dict(), ensure_ascii=False),
            raw_json=json.dumps(raw_data, ensure_ascii=False),
            avatar_path=avatar_path
        )

        db.add(character)
        db.commit()
        db.refresh(character)

        logger.info(f"Character imported: {character.name} (ID: {character.id})")
        return character

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Character import failed: {e}")
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


@router.get("/{character_id}/compatibility")
def get_character_compatibility(character_id: str, db: Session = Depends(get_db)):
    """Return a safe, data-only compatibility report for the imported card."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    try:
        normalized = json.loads(character.normalized_json) if character.normalized_json else {}
    except (json.JSONDecodeError, TypeError):
        normalized = {}
    from ..services.cards.compatibility import build_compatibility_report
    report = build_compatibility_report(normalized)
    return {"character_id": character.id, "character_name": character.name, **report}


@router.get("/{character_id}", response_model=CharacterResponse)
def get_character(character_id: str, db: Session = Depends(get_db)):
    """Get character by ID."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    return character


@router.put("/{character_id}", response_model=CharacterResponse)
def update_character(
    character_id: str,
    update: CharacterUpdate,
    db: Session = Depends(get_db)
):
    """Update character basic info."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")

    update_data = update.model_dump(exclude_unset=True)

    # Update basic fields
    for field in ["name", "description", "personality", "scenario", "first_message"]:
        if field in update_data:
            setattr(character, field, update_data[field])

    # Update normalized_json if provided
    if "normalized_json" in update_data and update_data["normalized_json"]:
        character.normalized_json = update_data["normalized_json"]
    else:
        # Update normalized_json with new basic fields
        try:
            norm = json.loads(character.normalized_json) if character.normalized_json else {}
        except json.JSONDecodeError:
            norm = {}

        norm["name"] = character.name
        norm["description"] = character.description
        norm["personality"] = character.personality
        norm["scenario"] = character.scenario
        norm["first_mes"] = character.first_message
        character.normalized_json = json.dumps(norm, ensure_ascii=False)

    db.commit()
    db.refresh(character)
    logger.info(f"Character updated: {character.name}")
    return character


@router.delete("/{character_id}")
def delete_character(character_id: str, db: Session = Depends(get_db)):
    """Delete a character and all related data."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")

    # Delete avatar file if exists
    if character.avatar_path:
        try:
            avatar_file = settings.avatars_dir / Path(character.avatar_path).name
            if avatar_file.exists():
                avatar_file.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete avatar file: {e}")

    db.delete(character)
    db.commit()
    logger.info(f"Character deleted: {character_id}")
    return {"success": True}


@router.get("/{character_id}/export")
def export_character(character_id: str, db: Session = Depends(get_db)):
    """Export character as JSON in V3 format."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")

    try:
        norm_dict = json.loads(character.normalized_json) if character.normalized_json else {}
        raw_dict = json.loads(character.raw_json) if character.raw_json else {}
    except json.JSONDecodeError:
        norm_dict = {}
        raw_dict = {}

    from ..services.character_parser.parser import CharacterCardNormalized
    normalized = CharacterCardNormalized()
    for key, value in norm_dict.items():
        if hasattr(normalized, key):
            setattr(normalized, key, value)

    export_data = export_character_v3(normalized, raw_dict)
    return export_data


@router.get("/{character_id}/lorebook", response_model=Lorebook)
def get_lorebook(character_id: str, db: Session = Depends(get_db)):
    """Get character's lorebook."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")

    try:
        norm = json.loads(character.normalized_json) if character.normalized_json else {}
    except json.JSONDecodeError:
        norm = {}

    character_book = norm.get("character_book", {})
    entries = character_book.get("entries", []) if isinstance(character_book, dict) else []

    return Lorebook(entries=[LorebookEntry(**e) for e in entries if isinstance(e, dict)])


@router.put("/{character_id}/lorebook", response_model=Lorebook)
def update_lorebook(
    character_id: str,
    lorebook: Lorebook,
    db: Session = Depends(get_db)
):
    """Update character's lorebook."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")

    try:
        norm = json.loads(character.normalized_json) if character.normalized_json else {}
    except json.JSONDecodeError:
        norm = {}

    entries_dicts = [e.model_dump() for e in lorebook.entries]
    norm["character_book"] = {"entries": entries_dicts}
    character.normalized_json = json.dumps(norm, ensure_ascii=False)

    db.commit()
    return lorebook
