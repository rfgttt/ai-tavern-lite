from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.logging import logger
from ..db.models import Memory
from ..db.session import get_db
from ..schemas import MemoryCreate, MemoryResponse, MemoryUpdate
from ..services.memory.service import MemoryDuplicateError, MemoryService

router = APIRouter(tags=["memory"])


def _duplicate_detail(error: MemoryDuplicateError) -> dict:
    memory = error.memory
    return {
        "code": "memory_duplicate",
        "message": str(error),
        "memory_id": memory.id,
        "enabled": memory.enabled,
        "category": MemoryService.normalize_category(memory.category),
        "scope": MemoryService.scope_name(memory.character_id, memory.session_id),
    }


@router.get("/memories", response_model=List[MemoryResponse])
def list_memories(
    character_id: Optional[str] = None,
    session_id: Optional[str] = None,
    scope: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List memories with exact or effective scope filtering."""
    query = db.query(Memory)

    try:
        if scope:
            normalized_character_id = character_id
            normalized_session_id = session_id
            if scope in {"character", "session", "effective"} and (
                character_id or session_id
            ):
                normalized_character_id, normalized_session_id = (
                    MemoryService.resolve_scope_ids(
                        db,
                        character_id=character_id,
                        session_id=session_id,
                    )
                )
            query = query.filter(
                MemoryService.scope_filter(
                    scope,
                    character_id=normalized_character_id,
                    session_id=normalized_session_id,
                )
            )
        else:
            if character_id is not None:
                if character_id == "global":
                    query = query.filter(MemoryService.scope_filter("global"))
                else:
                    query = query.filter(Memory.character_id == character_id)
            if session_id is not None:
                query = query.filter(Memory.session_id == session_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if category:
        query = query.filter(
            Memory.category.in_(MemoryService.category_filter_values(category))
        )

    if search:
        query = query.filter(Memory.content.contains(search))

    return query.order_by(Memory.updated_at.desc()).all()


@router.post("/memories", response_model=MemoryResponse)
def create_memory(memory_data: MemoryCreate, db: Session = Depends(get_db)):
    """Create a memory, warning on an exact duplicate unless explicitly forced."""
    try:
        return MemoryService.add_memory(
            db,
            content=memory_data.content,
            category=memory_data.category,
            importance=memory_data.importance,
            keywords=memory_data.keywords,
            character_id=memory_data.character_id,
            session_id=memory_data.session_id,
            allow_duplicate=memory_data.allow_duplicate,
        )
    except MemoryDuplicateError as error:
        raise HTTPException(status_code=409, detail=_duplicate_detail(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.put("/memories/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: str,
    update: MemoryUpdate,
    db: Session = Depends(get_db),
):
    """Update a memory without implicitly changing its scope."""
    memory = db.query(Memory).filter(Memory.id == memory_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")

    update_data = update.model_dump(exclude_unset=True)
    allow_duplicate = bool(update_data.pop("allow_duplicate", False))
    try:
        return MemoryService.update_memory(
            db,
            memory,
            update_data,
            allow_duplicate=allow_duplicate,
        )
    except MemoryDuplicateError as error:
        raise HTTPException(status_code=409, detail=_duplicate_detail(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str, db: Session = Depends(get_db)):
    """Delete a memory."""
    memory = db.query(Memory).filter(Memory.id == memory_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")

    db.delete(memory)
    db.commit()
    logger.info("Memory deleted: %s", memory_id)
    return {"success": True}
