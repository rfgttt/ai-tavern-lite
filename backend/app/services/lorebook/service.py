import re
from typing import List, Dict, Any, Set
from ...core.logging import logger


class LorebookEntry:
    def __init__(self, data: dict):
        self.id = data.get("id", 0)
        self.keys = data.get("keys", []) or []
        self.secondary_keys = data.get("secondary_keys", []) or []
        self.comment = data.get("comment", "")
        self.content = data.get("content", "")
        self.constant = data.get("constant", False)
        self.selective = data.get("selective", False)
        self.enabled = data.get("enabled", True)
        self.insertion_order = data.get("insertion_order", 0)
        self.position = data.get("position", "before_char")
        self.use_regex = data.get("use_regex", False)
        self.probability = data.get("probability", 100)
        self.extensions = data.get("extensions", {})


class LorebookService:
    @staticmethod
    def parse_entries(character_book: dict) -> List[LorebookEntry]:
        """Parse lorebook entries from character_book dict."""
        if not character_book or not isinstance(character_book, dict):
            return []

        entries_data = character_book.get("entries", [])
        if not isinstance(entries_data, list):
            return []

        entries = []
        for entry_data in entries_data:
            if isinstance(entry_data, dict):
                entries.append(LorebookEntry(entry_data))

        return entries

    @staticmethod
    def get_triggered_entries(
        entries: List[LorebookEntry],
        recent_text: str,
        scan_depth: int = 2000
    ) -> List[LorebookEntry]:
        """
        Get triggered lorebook entries.
        - constant entries always trigger (if enabled)
        - keyword entries trigger if any key matches in recent text
        """
        if not entries:
            return []

        triggered = []
        seen_contents: Set[str] = set()

        # Limit scan text length
        scan_text = recent_text[-scan_depth:] if len(recent_text) > scan_depth else recent_text
        scan_lower = scan_text.lower()

        for entry in entries:
            if not entry.enabled:
                continue

            # Skip empty content
            if not entry.content.strip():
                continue

            is_triggered = False

            if entry.constant:
                is_triggered = True
            else:
                # Check keys
                for key in entry.keys:
                    if not key:
                        continue
                    if LorebookService._key_matches(key, entry.use_regex, scan_text, scan_lower):
                        # If selective, also check secondary keys
                        if entry.selective and entry.secondary_keys:
                            if any(LorebookService._key_matches(sk, entry.use_regex, scan_text, scan_lower)
                                   for sk in entry.secondary_keys):
                                is_triggered = True
                                break
                        else:
                            is_triggered = True
                            break

            if is_triggered:
                # Probability check (0-100)
                prob = max(0, min(100, entry.probability))
                if prob < 100:
                    import random
                    if random.randint(1, 100) > prob:
                        continue

                # Deduplicate by content
                if entry.content not in seen_contents:
                    triggered.append(entry)
                    seen_contents.add(entry.content)

        # Sort by insertion_order
        triggered.sort(key=lambda e: e.insertion_order)
        return triggered

    @staticmethod
    def _key_matches(key: str, use_regex: bool, text: str, text_lower: str) -> bool:
        """Check if a key matches the text."""
        if not key:
            return False

        try:
            if use_regex:
                return bool(re.search(key, text, re.IGNORECASE))
            else:
                return key.lower() in text_lower
        except re.error:
            # Invalid regex, fall back to plain text
            logger.warning(f"Invalid regex in lorebook key: {key}")
            return key.lower() in text_lower

    @staticmethod
    def build_lorebook_text(entries: List[LorebookEntry]) -> str:
        """Build combined lorebook text from triggered entries."""
        if not entries:
            return ""

        parts = ["【世界书设定】"]
        for entry in entries:
            title = entry.comment if entry.comment else f"条目 #{entry.id}"
            parts.append(f"- {title}: {entry.content.strip()}")

        return "\n".join(parts)
