from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path

EXCLUDED_PARTS = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", "dist", ".vite", "self-test-results", "server-data",
}
EXCLUDED_NAMES = {".env", ".env.production"}
EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pyc", ".log", ".zip"}


def should_include(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if path.name in EXCLUDED_NAMES:
        return False
    if path.name.startswith(".env.") and path.name not in {".env.example", ".env.production.example"}:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name.endswith((".db-wal", ".db-shm", ".db-journal")):
        return False
    if relative.parts[:2] == ("backend", "data"):
        return False
    return True


def build_release(root: Path, output: Path) -> None:
    root = root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ai-tavern-release-") as temp_dir:
        staging = Path(temp_dir) / "AI-Tavern-Lite"
        for source in root.rglob("*"):
            if not source.is_file() or not should_include(source, root):
                continue
            destination = staging / source.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for file_path in staging.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, file_path.relative_to(staging.parent))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a secret- and runtime-data-free release archive")
    parser.add_argument("--output", default="AI-Tavern-Lite-release.zip")
    args = parser.parse_args()
    build_release(Path(__file__).resolve().parent.parent, Path(args.output))
    print(Path(args.output).resolve())
