from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.logging import logger
from ..db.models import Memory
from ..db.session import get_db
from ..schemas import MemoryCreate, MemoryResponse, MemoryUpdate
from ..services.memory.service import MemoryService

router = APIRouter(tags=["memory"])


@router.get("/memories", response_model=List[MemoryResponse])
def list_memories(
    character_id: Optional[str] = None,
    session_id: Optional[str] = None,
    scope: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List memories with exact or effective scope filtering.

    New clients should pass scope=global|character|session|effective. When scope
    is omitted, the previous character_id filter remains available for backward
    compatibility, except that character_id=global now correctly excludes
    session-scoped legacy rows.
    """
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
                    query = query.filter(
                        MemoryService.scope_filter("global")
                    )
                else:
                    query = query.filter(Memory.character_id == character_id)
            if session_id is not None:
                query = query.filter(Memory.session_id == session_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if category:
        query = query.filter(Memory.category == category)

    if search:
        query = query.filter(Memory.content.contains(search))

    return query.order_by(Memory.updated_at.desc()).all()


@router.post("/memories", response_model=MemoryResponse)
def create_memory(memory_data: MemoryCreate, db: Session = Depends(get_db)):
    """Create a new memory."""
    content = memory_data.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="记忆内容不能为空")
    try:
        return MemoryService.add_memory(
            db,
            content=content,
            category=memory_data.category,
            importance=memory_data.importance,
            keywords=memory_data.keywords,
            character_id=memory_data.character_id,
            session_id=memory_data.session_id,
        )
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
    if "content" in update_data:
        update_data["content"] = (update_data["content"] or "").strip()
        if not update_data["content"]:
            raise HTTPException(status_code=422, detail="记忆内容不能为空")
    for field, value in update_data.items():
        setattr(memory, field, value)

    db.commit()
    db.refresh(memory)
    return memory


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
