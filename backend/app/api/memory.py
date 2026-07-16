from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from ..db.session import get_db
from ..db.models import Memory
from ..schemas import MemoryResponse, MemoryCreate, MemoryUpdate
from ..services.memory.service import MemoryService
from ..core.logging import logger

router = APIRouter(tags=["memory"])


@router.get("/memories", response_model=List[MemoryResponse])
def list_memories(
    character_id: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List memories with optional filters."""
    query = db.query(Memory)

    if character_id is not None:
        if character_id == "global":
            query = query.filter(Memory.character_id.is_(None))
        else:
            query = query.filter(Memory.character_id == character_id)

    if category:
        query = query.filter(Memory.category == category)

    if search:
        query = query.filter(Memory.content.contains(search))

    memories = query.order_by(Memory.updated_at.desc()).all()
    return memories


@router.post("/memories", response_model=MemoryResponse)
def create_memory(memory_data: MemoryCreate, db: Session = Depends(get_db)):
    """Create a new memory."""
    content = memory_data.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="记忆内容不能为空")
    memory = MemoryService.add_memory(
        db,
        content=content,
        category=memory_data.category,
        importance=memory_data.importance,
        keywords=memory_data.keywords,
        character_id=memory_data.character_id,
        session_id=memory_data.session_id
    )
    return memory


@router.put("/memories/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: str,
    update: MemoryUpdate,
    db: Session = Depends(get_db)
):
    """Update a memory."""
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
    logger.info(f"Memory deleted: {memory_id}")
    return {"success": True}
