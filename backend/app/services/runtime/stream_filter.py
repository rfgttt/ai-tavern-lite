from __future__ import annotations


class RuntimeStreamFilter:
    """Stream player-visible text while suppressing metadata blocks appended by the model."""

    markers = (
        "<tavern_state",
        "<updatevariable",
        "<update_variable",
        "<dice",
        "<battlecheck",
        "<battle",
        "<text>",
        "<text ",
        "<status>",
        "<status ",
    )

    def __init__(self):
        self.buffer = ""
        self.hidden = False

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        if self.hidden:
            self.buffer += chunk
            return ""

        self.buffer += chunk
        lower = self.buffer.lower()
        starts = [lower.find(marker) for marker in self.markers if lower.find(marker) >= 0]
        if starts:
            index = min(starts)
            visible = self.buffer[:index]
            self.buffer = self.buffer[index:]
            self.hidden = True
            return visible

        hold = 0
        max_check = min(len(self.buffer), max(len(marker) for marker in self.markers) - 1)
        lower = self.buffer.lower()
        for size in range(1, max_check + 1):
            suffix = lower[-size:]
            if any(marker.startswith(suffix) for marker in self.markers):
                hold = size
        if hold:
            visible = self.buffer[:-hold]
            self.buffer = self.buffer[-hold:]
        else:
            visible = self.buffer
            self.buffer = ""
        return visible

    def finish(self) -> str:
        if self.hidden:
            return ""
        remaining = self.buffer
        self.buffer = ""
        return remaining
