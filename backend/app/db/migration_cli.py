from __future__ import annotations

import argparse

from alembic import command

from .migrations import (
    alembic_config,
    get_database_revision,
    get_head_revision,
    validate_database_schema,
)
from .session import engine, init_db


def _print_status() -> None:
    current = get_database_revision(engine)
    head = get_head_revision()
    print(f"Current revision: {current or 'unversioned'}")
    print(f"Head revision:    {head}")
    print("Status:           up to date" if current == head else "Status:           upgrade required")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Tavern Lite database migration helper")
    parser.add_argument(
        "action",
        choices=("status", "upgrade", "validate", "history", "heads"),
        nargs="?",
        default="status",
    )
    args = parser.parse_args()

    if args.action == "status":
        _print_status()
    elif args.action == "upgrade":
        result = init_db(engine)
        print(
            f"Database upgraded and validated: revision={result.revision}, "
            f"tables={result.table_count}"
        )
    elif args.action == "validate":
        result = validate_database_schema(engine)
        print(
            f"Database schema is valid: revision={result.revision}, "
            f"tables={result.table_count}"
        )
    elif args.action == "history":
        command.history(alembic_config(engine), verbose=True)
    elif args.action == "heads":
        command.heads(alembic_config(engine), verbose=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
