from typing import List, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ...core.logging import logger
from ...db.models import Character, ChatSession, Memory


class MemoryService:
    VALID_SCOPES = {"global", "character", "session", "effective"}

    @staticmethod
    def resolve_scope_ids(
        db: Session,
        character_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Validate and normalize the identifiers that define a memory scope.

        Scope is derived from the identifier pair instead of a separate database
        column:
        - global: character_id=None, session_id=None
        - character: character_id=<id>, session_id=None
        - session: session_id=<id>; character_id is normalized to the session owner
        """
        if session_id:
            chat_session = (
                db.query(ChatSession)
                .filter(ChatSession.id == session_id)
                .first()
            )
            if not chat_session:
                raise ValueError("会话不存在")
            if character_id and character_id != chat_session.character_id:
                raise ValueError("会话不属于指定角色")
            return chat_session.character_id, chat_session.id

        if character_id:
            character_exists = (
                db.query(Character.id)
                .filter(Character.id == character_id)
                .first()
            )
            if not character_exists:
                raise ValueError("角色不存在")
            return character_id, None

        return None, None

    @staticmethod
    def scope_filter(
        scope: str,
        character_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """Build an exact SQL filter for a memory scope."""
        if scope not in MemoryService.VALID_SCOPES:
            raise ValueError("无效的记忆作用域")

        global_scope = and_(
            Memory.character_id.is_(None),
            Memory.session_id.is_(None),
        )

        if scope == "global":
            return global_scope

        if scope == "character":
            if not character_id:
                raise ValueError("角色作用域需要 character_id")
            return and_(
                Memory.character_id == character_id,
                Memory.session_id.is_(None),
            )

        if scope == "session":
            if not session_id:
                raise ValueError("会话作用域需要 session_id")
            return Memory.session_id == session_id

        effective_scopes = [global_scope]
        if character_id:
            effective_scopes.append(
                and_(
                    Memory.character_id == character_id,
                    Memory.session_id.is_(None),
                )
            )
        if session_id:
            effective_scopes.append(Memory.session_id == session_id)
        return or_(*effective_scopes)

    @staticmethod
    def get_relevant_memories(
        db: Session,
        character_id: Optional[str] = None,
        session_id: Optional[str] = None,
        query_text: str = "",
        max_entries: int = 12,
    ) -> List[Memory]:
        """Get memories visible in the current character/session context.

        Only global memories, character-shared memories, and memories from the
        current session are eligible. Session memories from sibling sessions are
        never included, including legacy rows whose character_id is null.
        """
        query = db.query(Memory).filter(
            Memory.enabled.is_(True),
            MemoryService.scope_filter(
                "effective",
                character_id=character_id,
                session_id=session_id,
            ),
        )
        all_memories = query.all()

        if not all_memories:
            return []

        query_lower = query_text.lower()
        scored = []

        for mem in all_memories:
            score = mem.importance

            if mem.keywords and query_text:
                keywords = [
                    keyword.strip().lower()
                    for keyword in mem.keywords.split(",")
                    if keyword.strip()
                ]
                for keyword in keywords:
                    if keyword in query_lower:
                        score += 0.3

            scored.append((score, mem))

        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [memory for _, memory in scored[:max_entries]]

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
        text = user_message.strip()

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
                potential_memories.append(
                    {
                        "category": category,
                        "content": text.strip(),
                        "importance": 0.6,
                        "keywords": text[:30],
                    }
                )
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
        session_id: Optional[str] = None,
    ) -> Memory:
        """Add a memory after validating and normalizing its scope."""
        character_id, session_id = MemoryService.resolve_scope_ids(
            db,
            character_id=character_id,
            session_id=session_id,
        )
        memory = Memory(
            character_id=character_id,
            session_id=session_id,
            category=category,
            content=content,
            importance=importance,
            keywords=keywords,
            enabled=True,
        )
        db.add(memory)
        db.commit()
        db.refresh(memory)
        logger.info("Memory added: %s - %s...", category, content[:50])
        return memory
