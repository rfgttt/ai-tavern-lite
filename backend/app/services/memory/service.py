import threading
import unicodedata
from typing import List, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ...core.logging import logger
from ...db.models import Character, ChatSession, Memory


class MemoryDuplicateError(Exception):
    """Raised when a manual memory write matches an existing exact record."""

    def __init__(self, memory: Memory):
        self.memory = memory
        state = "已禁用" if not memory.enabled else "已启用"
        super().__init__(f"当前作用域和分类中已存在内容相同的记忆（{state}）")


class MemoryService:
    VALID_SCOPES = {"global", "character", "session", "effective"}
    CATEGORY_ALIASES = {"user_fact": "fact"}
    AUTO_DEDUPE_CATEGORIES = {"fact", "preference", "relationship", "definition"}
    _write_lock = threading.RLock()

    @staticmethod
    def normalize_category(category: str) -> str:
        """Normalize known legacy category aliases without changing custom labels."""
        cleaned = (category or "general").strip() or "general"
        return MemoryService.CATEGORY_ALIASES.get(cleaned, cleaned)

    @staticmethod
    def category_filter_values(category: str) -> set[str]:
        """Return stored category values equivalent to a requested category."""
        normalized = MemoryService.normalize_category(category)
        values = {normalized}
        values.update(
            alias
            for alias, canonical in MemoryService.CATEGORY_ALIASES.items()
            if canonical == normalized
        )
        return values

    @staticmethod
    def normalize_content(content: str) -> str:
        """Apply only non-semantic normalization used for exact duplicate checks."""
        normalized_newlines = (content or "").replace("\r\n", "\n").replace("\r", "\n")
        return unicodedata.normalize("NFC", normalized_newlines).strip()

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
    def scope_name(
        character_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        if session_id:
            return "session"
        if character_id:
            return "character"
        return "global"

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
    def find_exact_duplicate(
        db: Session,
        *,
        content: str,
        category: str,
        character_id: Optional[str],
        session_id: Optional[str],
        exclude_memory_id: Optional[str] = None,
    ) -> Optional[Memory]:
        """Find an exact duplicate within one semantic memory scope.

        Existing disabled rows and legacy ``user_fact`` rows participate. Internal
        whitespace, punctuation, casing and wording are intentionally preserved.
        """
        normalized_content = MemoryService.normalize_content(content)
        normalized_category = MemoryService.normalize_category(category)
        scope = MemoryService.scope_name(character_id, session_id)
        query = db.query(Memory).filter(
            MemoryService.scope_filter(
                scope,
                character_id=character_id,
                session_id=session_id,
            )
        )
        if exclude_memory_id:
            query = query.filter(Memory.id != exclude_memory_id)

        for candidate in query.all():
            if MemoryService.normalize_category(candidate.category) != normalized_category:
                continue
            if MemoryService.normalize_content(candidate.content) == normalized_content:
                return candidate
        return None

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
            category = MemoryService.normalize_category(mem.category)
            parts.append(f"- [{category}] {mem.content.strip()}")

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
            ("我是", "fact"),
            ("我叫", "fact"),
            ("我喜欢", "preference"),
            ("我讨厌", "preference"),
            ("我住在", "fact"),
            ("我的", "fact"),
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
        *,
        allow_duplicate: bool = False,
        skip_duplicate: bool = False,
    ) -> Memory:
        """Add a memory after validating its scope and exact duplicate identity."""
        with MemoryService._write_lock:
            character_id, session_id = MemoryService.resolve_scope_ids(
                db,
                character_id=character_id,
                session_id=session_id,
            )
            normalized_content = MemoryService.normalize_content(content)
            if not normalized_content:
                raise ValueError("记忆内容不能为空")
            normalized_category = MemoryService.normalize_category(category)

            duplicate = MemoryService.find_exact_duplicate(
                db,
                content=normalized_content,
                category=normalized_category,
                character_id=character_id,
                session_id=session_id,
            )
            if duplicate:
                if skip_duplicate:
                    logger.debug("Duplicate auto-extracted memory skipped: %s", duplicate.id)
                    return duplicate
                if not allow_duplicate:
                    raise MemoryDuplicateError(duplicate)

            memory = Memory(
                character_id=character_id,
                session_id=session_id,
                category=normalized_category,
                content=normalized_content,
                importance=importance,
                keywords=keywords,
                enabled=True,
            )
            db.add(memory)
            db.commit()
            db.refresh(memory)
            logger.info("Memory added: %s - %s...", normalized_category, normalized_content[:50])
            return memory

    @staticmethod
    def update_memory(
        db: Session,
        memory: Memory,
        update_data: dict,
        *,
        allow_duplicate: bool = False,
    ) -> Memory:
        """Update a memory without changing scope or silently creating duplicates."""
        with MemoryService._write_lock:
            candidate_content = MemoryService.normalize_content(
                update_data.get("content", memory.content)
            )
            if not candidate_content:
                raise ValueError("记忆内容不能为空")
            candidate_category = MemoryService.normalize_category(
                update_data.get("category", memory.category)
            )

            identity_changed = (
                candidate_content != MemoryService.normalize_content(memory.content)
                or candidate_category != MemoryService.normalize_category(memory.category)
            )
            if identity_changed:
                duplicate = MemoryService.find_exact_duplicate(
                    db,
                    content=candidate_content,
                    category=candidate_category,
                    character_id=memory.character_id,
                    session_id=memory.session_id,
                    exclude_memory_id=memory.id,
                )
                if duplicate and not allow_duplicate:
                    raise MemoryDuplicateError(duplicate)

            if "content" in update_data:
                update_data["content"] = candidate_content
            if "category" in update_data:
                update_data["category"] = candidate_category
            for field, value in update_data.items():
                setattr(memory, field, value)

            db.commit()
            db.refresh(memory)
            return memory
