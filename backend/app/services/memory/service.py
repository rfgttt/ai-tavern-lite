from typing import List, Optional
from sqlalchemy.orm import Session
from ...db.models import Memory
from ...core.logging import logger


class MemoryService:
    @staticmethod
    def get_relevant_memories(
        db: Session,
        character_id: Optional[str] = None,
        query_text: str = "",
        max_entries: int = 12
    ) -> List[Memory]:
        """Get relevant memories based on keywords and importance."""
        query = db.query(Memory).filter(Memory.enabled == True)

        # Character-specific memories first
        if character_id:
            char_memories = query.filter(Memory.character_id == character_id).all()
        else:
            char_memories = []

        # Global memories (no character_id)
        global_memories = query.filter(Memory.character_id.is_(None)).all()

        all_memories = char_memories + global_memories

        if not all_memories:
            return []

        # Score memories
        query_lower = query_text.lower()
        scored = []

        for mem in all_memories:
            score = mem.importance  # Base score from importance

            # Keyword match bonus
            if mem.keywords and query_text:
                keywords = [k.strip().lower() for k in mem.keywords.split(",") if k.strip()]
                for kw in keywords:
                    if kw in query_lower:
                        score += 0.3

            # Recency bonus (simplified - just use updated_at ordering later)
            scored.append((score, mem))

        # Sort by score descending, then by updated_at descending
        scored.sort(key=lambda x: (x[0], x[1].updated_at), reverse=True)

        # Return top N
        return [mem for _, mem in scored[:max_entries]]

    @staticmethod
    def build_memory_text(memories: List[Memory]) -> str:
        """Build memory section text for prompt."""
        if not memories:
            return ""

        parts = ["【长期记忆】"]
        for mem in memories:
            parts.append(f"- [{mem.category}] {mem.content.strip()}")

        return "\n".join(parts)

    @staticmethod
    def extract_memories_simple(user_message: str, ai_message: str) -> List[dict]:
        """
        Simple rule-based memory extraction (for mock mode / testing).
        Returns list of potential memory dicts.
        """
        potential_memories = []

        # Look for factual statements in user message
        text = user_message.strip()

        # Simple patterns for facts
        fact_patterns = [
            ("我是", "user_fact"),
            ("我叫", "user_fact"),
            ("我喜欢", "preference"),
            ("我讨厌", "preference"),
            ("我住在", "user_fact"),
            ("我的", "user_fact"),
        ]

        for pattern, category in fact_patterns:
            if pattern in text and len(text) < 200:
                potential_memories.append({
                    "category": category,
                    "content": text.strip(),
                    "importance": 0.6,
                    "keywords": text[:30]
                })
                break

        return potential_memories

    @staticmethod
    def add_memory(
        db: Session,
        content: str,
        category: str = "general",
        importance: float = 0.5,
        keywords: str = "",
        character_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Memory:
        """Add a new memory."""
        memory = Memory(
            character_id=character_id,
            session_id=session_id,
            category=category,
            content=content,
            importance=importance,
            keywords=keywords,
            enabled=True
        )
        db.add(memory)
        db.commit()
        db.refresh(memory)
        logger.info(f"Memory added: {category} - {content[:50]}...")
        return memory
