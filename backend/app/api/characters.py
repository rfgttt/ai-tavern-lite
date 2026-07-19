from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
from typing import List, Literal
import json
import os
from pathlib import Path
import uuid
import shutil

from ..db.session import get_db
from ..db.models import Character, ChatSession, Message, Memory
from ..schemas import (
    CharacterResponse, CharacterUpdate, CharacterCreate,
    CharacterSessionOptionsResponse, CharacterCardSecurityScanResponse,
    Lorebook, LorebookEntry
)
from ..services.character_parser.parser import (
    parse_json_character, parse_png_character, export_character_v3,
    replace_template_vars, validate_character_card_v3,
)
from ..core.config import settings
from ..core.logging import logger
from ..services.runtime.session_service import character_profile
from ..services.runtime.state_engine import build_initial_state
from ..services.settings_service import SettingsService
from ..services.card_security import (
    apply_security_metadata,
    is_quarantined,
    sanitize_character_card,
    scan_character_card,
)

router = APIRouter(prefix="/characters", tags=["characters"])

MAX_UPLOAD_SIZE = settings.max_upload_size_mb * 1024 * 1024


def _validate_opening_messages(first_message: str, alternate_greetings: list[str]) -> None:
    default_text = str(first_message or "").strip()
    seen = {default_text} if default_text else set()
    for index, greeting in enumerate(alternate_greetings):
        text = str(greeting or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail=f"备用开场白 {index + 1} 不能为空")
        if text in seen:
            raise HTTPException(status_code=400, detail="开场白不能重复")
        seen.add(text)


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


@router.post("", response_model=CharacterResponse, status_code=201)
def create_character(
    payload: CharacterCreate,
    db: Session = Depends(get_db),
):
    """Create a character from the built-in editor without requiring a card file."""
    try:
        normalized = json.loads(payload.normalized_json or "{}")
        raw_data = json.loads(payload.raw_json or "{}")
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"角色数据不是有效 JSON: {exc}")

    if not isinstance(normalized, dict) or not isinstance(raw_data, dict):
        raise HTTPException(status_code=400, detail="角色数据必须是 JSON 对象")

    _validate_opening_messages(payload.first_message, payload.alternate_greetings)
    normalized.update({
        "name": payload.name.strip(),
        "description": payload.description,
        "personality": payload.personality,
        "scenario": payload.scenario,
        "first_mes": payload.first_message.strip(),
        "alternate_greetings": payload.alternate_greetings,
    })

    character = Character(
        name=payload.name.strip(),
        description=payload.description,
        personality=payload.personality,
        scenario=payload.scenario,
        first_message=payload.first_message.strip(),
        normalized_json=json.dumps(normalized, ensure_ascii=False),
        raw_json=json.dumps(raw_data, ensure_ascii=False),
        avatar_path=payload.avatar_path,
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    logger.info(f"Character created: {character.name} (ID: {character.id})")
    return character


@router.post("/security/scan", response_model=CharacterCardSecurityScanResponse)
async def scan_character_upload(file: UploadFile = File(...)):
    """Statically scan a JSON or PNG card without executing code or fetching URLs."""
    content = await _read_upload_limited(file)
    filename = file.filename or "character-card"
    normalized, raw_data, _ = _parse_character_upload(filename, content)
    report = scan_character_card(normalized.to_dict(), raw_data)
    return {
        "filename": filename,
        "card_name": normalized.name or "未知角色",
        "report": report,
    }


def _parse_character_upload(filename: str, content: bytes):
    filename_lower = filename.lower()
    if filename_lower.endswith(".json"):
        try:
            json_data = json.loads(content.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise HTTPException(status_code=400, detail=f"JSON 解析失败: {error}")
        normalized, raw_data = parse_json_character(json_data)
        return normalized, raw_data, None
    if filename_lower.endswith(".png"):
        try:
            normalized, raw_data, avatar_bytes = parse_png_character(content)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return normalized, raw_data, avatar_bytes
    raise HTTPException(status_code=400, detail="不支持的文件格式，请上传 .json 或 .png 角色卡文件")


def _security_mode_payload(normalized: dict, raw_data: dict, report: dict, mode: str):
    if not report.get("can_import_safe", True):
        raise HTTPException(status_code=400, detail="角色卡结构过深或过大，已阻止导入")
    if mode == "safe_copy":
        return sanitize_character_card(normalized, raw_data, report)[:2]
    if mode == "quarantine":
        quarantined = apply_security_metadata(normalized, report, "quarantine")
        return quarantined, raw_data
    if mode == "original":
        if not report.get("can_import_original", False):
            raise HTTPException(
                status_code=400,
                detail="该角色卡包含高风险提示词注入或可执行内容，只能隔离保存或生成安全副本",
            )
        reviewed = apply_security_metadata(normalized, report, "original_reviewed")
        return reviewed, raw_data
    raise HTTPException(status_code=400, detail="security_mode 必须是 safe_copy、quarantine 或 original")


@router.post("/import", response_model=CharacterResponse)
async def import_character(
    file: UploadFile = File(...),
    security_mode: Literal["safe_copy", "quarantine", "original"] = Form("safe_copy"),
    db: Session = Depends(get_db),
):
    """Import a card after applying the selected security policy."""
    content = await _read_upload_limited(file)
    filename = file.filename or "character-card"
    avatar_path = ""
    avatar_file: Path | None = None

    try:
        normalized, raw_data, avatar_bytes = _parse_character_upload(filename, content)
        normalized_dict = normalized.to_dict()
        report = scan_character_card(normalized_dict, raw_data)
        normalized_dict, stored_raw = _security_mode_payload(
            normalized_dict, raw_data, report, security_mode
        )

        if avatar_bytes is not None:
            avatar_filename = f"{uuid.uuid4()}.png"
            avatar_file = settings.avatars_dir / avatar_filename
            with avatar_file.open("wb") as output:
                output.write(avatar_bytes)
            avatar_path = f"/avatars/{avatar_filename}"

        display_name = str(normalized_dict.get("name") or "未知角色")
        if security_mode == "quarantine":
            suffix = "（隔离）"
            display_name = (display_name[: max(1, 200 - len(suffix))] + suffix)[:200]

        character = Character(
            name=display_name,
            description=str(normalized_dict.get("description") or ""),
            personality=str(normalized_dict.get("personality") or ""),
            scenario=str(normalized_dict.get("scenario") or ""),
            first_message=str(normalized_dict.get("first_mes") or ""),
            normalized_json=json.dumps(normalized_dict, ensure_ascii=False),
            raw_json=json.dumps(stored_raw, ensure_ascii=False),
            avatar_path=avatar_path,
        )
        db.add(character)
        db.commit()
        db.refresh(character)
        logger.info(
            "Character imported: %s (ID: %s) security_mode=%s risk=%s",
            character.name, character.id, security_mode, report.get("risk_level"),
        )
        return character
    except HTTPException:
        if avatar_file and avatar_file.exists():
            avatar_file.unlink(missing_ok=True)
        raise
    except Exception as error:
        db.rollback()
        if avatar_file and avatar_file.exists():
            avatar_file.unlink(missing_ok=True)
        logger.error("Character import failed: %s", error)
        raise HTTPException(status_code=500, detail=f"导入失败: {error}")


@router.get("/{character_id}/security", response_model=CharacterCardSecurityScanResponse)
def get_character_security(character_id: str, db: Session = Depends(get_db)):
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    try:
        normalized = json.loads(character.normalized_json) if character.normalized_json else {}
        raw_data = json.loads(character.raw_json) if character.raw_json else normalized
    except (json.JSONDecodeError, TypeError):
        normalized, raw_data = {}, {}
    return {
        "filename": f"{character.name}.json",
        "card_name": character.name,
        "report": scan_character_card(normalized, raw_data),
    }


@router.post("/{character_id}/security/safe-copy", response_model=CharacterResponse, status_code=201)
def create_character_safe_copy(character_id: str, db: Session = Depends(get_db)):
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    try:
        normalized = json.loads(character.normalized_json) if character.normalized_json else {}
        raw_data = json.loads(character.raw_json) if character.raw_json else normalized
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="角色卡数据损坏，无法生成安全副本")

    report = scan_character_card(normalized, raw_data)
    if not report.get("can_import_safe", True):
        raise HTTPException(status_code=400, detail="角色卡结构过深或过大，无法生成安全副本")
    safe, safe_raw, _ = sanitize_character_card(normalized, raw_data, report)
    suffix = "（安全副本）"
    base_name = str(safe.get("name") or character.name or "未知角色")
    safe_name = (base_name[: max(1, 200 - len(suffix))] + suffix)[:200]
    safe["name"] = safe_name
    if isinstance(safe_raw.get("data"), dict):
        safe_raw["data"]["name"] = safe_name
    else:
        safe_raw["name"] = safe_name

    avatar_path = ""
    copied_avatar: Path | None = None
    if character.avatar_path:
        source_avatar = settings.avatars_dir / Path(character.avatar_path).name
        if source_avatar.exists():
            copied_avatar = settings.avatars_dir / f"{uuid.uuid4()}{source_avatar.suffix.lower() or '.png'}"
            shutil.copy2(source_avatar, copied_avatar)
            avatar_path = f"/avatars/{copied_avatar.name}"

    try:
        clone = Character(
            name=safe_name,
            description=str(safe.get("description") or ""),
            personality=str(safe.get("personality") or ""),
            scenario=str(safe.get("scenario") or ""),
            first_message=str(safe.get("first_mes") or ""),
            normalized_json=json.dumps(safe, ensure_ascii=False),
            raw_json=json.dumps(safe_raw, ensure_ascii=False),
            avatar_path=avatar_path,
        )
        db.add(clone)
        db.commit()
        db.refresh(clone)
        return clone
    except Exception:
        db.rollback()
        if copied_avatar and copied_avatar.exists():
            copied_avatar.unlink(missing_ok=True)
        raise


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


@router.get("/{character_id}/session-options", response_model=CharacterSessionOptionsResponse)
def get_character_session_options(character_id: str, db: Session = Depends(get_db)):
    """Return opening-message choices and the generated runtime state for the session wizard."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")

    try:
        normalized = json.loads(character.normalized_json) if character.normalized_json else {}
    except (json.JSONDecodeError, TypeError):
        normalized = {}
    if not isinstance(normalized, dict):
        normalized = {}
    if is_quarantined(normalized):
        raise HTTPException(
            status_code=423,
            detail="该角色卡处于安全隔离状态。请先在角色菜单中生成安全副本，再创建会话。",
        )

    settings_data = SettingsService.get_all_settings(db)
    username = settings_data.get("username", "用户")
    source_candidates: list[tuple[str, str, str, str, int | None]] = [
        ("default", "default", "默认开场白", character.first_message, None),
    ]
    alternate = normalized.get("alternate_greetings", [])
    if isinstance(alternate, list):
        for index, item in enumerate(alternate):
            if isinstance(item, str):
                source_candidates.append((f"alternate-{index}", "alternate", f"备用开场白 {index + 1}", item, index))

    greeting_options: list[dict] = []
    seen: set[str] = set()
    for key, kind, label, item, source_index in source_candidates:
        rendered = replace_template_vars(str(item or "").strip(), character.name, username)
        if rendered and rendered not in seen:
            greeting_options.append({
                "key": key,
                "kind": kind,
                "label": label,
                "content": rendered,
                "source_index": source_index,
            })
            seen.add(rendered)

    greetings = [option["content"] for option in greeting_options]
    profile = character_profile(character)
    initial_state = build_initial_state(profile, normalized, username=username)
    return {
        "character_id": character.id,
        "character_name": character.name,
        "greetings": greetings,
        "greeting_options": greeting_options,
        "runtime_profile": profile,
        "initial_state": initial_state,
    }


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

    for field in ["name", "description", "personality", "scenario", "first_message"]:
        if field in update_data:
            value = update_data[field]
            if field == "first_message" and isinstance(value, str):
                value = value.strip()
            setattr(character, field, value)

    if "normalized_json" in update_data and update_data["normalized_json"]:
        try:
            norm = json.loads(update_data["normalized_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"角色数据不是有效 JSON: {exc}")
    else:
        try:
            norm = json.loads(character.normalized_json) if character.normalized_json else {}
        except (json.JSONDecodeError, TypeError):
            norm = {}
    if not isinstance(norm, dict):
        raise HTTPException(status_code=400, detail="角色数据必须是 JSON 对象")

    alternate_greetings = update_data.get("alternate_greetings")
    if alternate_greetings is None:
        existing = norm.get("alternate_greetings", [])
        alternate_greetings = existing if isinstance(existing, list) else []
    if "alternate_greetings" in update_data or "first_message" in update_data:
        _validate_opening_messages(character.first_message, alternate_greetings)

    norm["name"] = character.name
    norm["description"] = character.description
    norm["personality"] = character.personality
    norm["scenario"] = character.scenario
    norm["first_mes"] = character.first_message
    norm["alternate_greetings"] = alternate_greetings
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
    validation_errors = validate_character_card_v3(export_data)
    if validation_errors:
        logger.error("Character export validation failed character=%s errors=%s", character_id, validation_errors)
        raise HTTPException(
            status_code=500,
            detail="角色卡导出校验失败：" + "；".join(validation_errors),
        )
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
    existing_book = norm.get("character_book")
    character_book = dict(existing_book) if isinstance(existing_book, dict) else {}
    character_book.setdefault("extensions", {})
    character_book["entries"] = entries_dicts
    norm["character_book"] = character_book
    character.normalized_json = json.dumps(norm, ensure_ascii=False)

    db.commit()
    return lorebook
