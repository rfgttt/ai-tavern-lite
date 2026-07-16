from __future__ import annotations

from typing import Callable, Iterable, TypeVar

T = TypeVar("T")


def build_section_budgets(context_budget: int) -> dict[str, int]:
    """Allocate a deterministic budget while guaranteeing recent chat space."""
    budget = max(0, int(context_budget))
    ratios = {
        "platform": 0.08,
        "character": 0.22,
        "runtime": 0.10,
        "lorebook": 0.20,
        "memory": 0.06,
        "post_history": 0.04,
        "history": 0.30,
    }
    allocated = {name: int(budget * ratio) for name, ratio in ratios.items()}
    allocated["history"] += budget - sum(allocated.values())
    return allocated


def truncate_text(text: str, max_tokens: int, estimate: Callable[[str], int]) -> str:
    if not text or max_tokens <= 0:
        return ""
    if estimate(text) <= max_tokens:
        return text

    suffix = "\n…（该部分因上下文预算截断）"
    if estimate(suffix) >= max_tokens:
        suffix = "…" if estimate("…") <= max_tokens else ""

    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        prefix = text[:mid].rstrip()
        candidate = prefix + suffix if prefix else suffix
        if estimate(candidate) <= max_tokens:
            low = mid
        else:
            high = mid - 1
    clipped = text[:low].rstrip()
    result = clipped + suffix if clipped else suffix
    # Estimators are intentionally approximate; retain a final defensive shrink.
    while result and estimate(result) > max_tokens:
        clipped = clipped[:-1].rstrip()
        result = clipped + suffix if clipped else suffix
        if not clipped and estimate(result) > max_tokens:
            return ""
    return result


def select_items_with_budget(
    items: Iterable[T],
    max_tokens: int,
    render: Callable[[T], str],
    estimate: Callable[[str], int],
) -> list[T]:
    selected: list[T] = []
    used = 0
    for item in items:
        cost = estimate(render(item))
        if cost <= 0:
            continue
        if used + cost > max_tokens:
            continue
        selected.append(item)
        used += cost
    return selected
