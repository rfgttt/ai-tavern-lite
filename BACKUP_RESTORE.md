# Complete Backup and Restore V1

AI Tavern Lite creates portable ZIP backups from the managed SQLite database and user-owned role assets.

## Included

- Characters and imported character-card data
- Personas and character groups
- Sessions, messages, runtime state, snapshots, and branches
- Long-term memories
- Avatars and imported character files
- Non-sensitive application settings

## Excluded from portable ZIP files

- API keys
- Custom authentication headers
- Passwords, tokens, and secret-like settings
- The local managed-storage database identity
- Logs, diagnostics, exports, caches, source code, and dependencies

When a restore is prepared, the current machine's sensitive settings and managed-storage identity are injected into the staged database. They are not taken from the uploaded backup.

## Restore transaction

1. The uploaded ZIP, manifest, hashes, paths, SQLite integrity, foreign keys, schema, Alembic revision, and record counts are validated.
2. The restored database and assets are staged under the managed data directory. The live database remains unchanged.
3. The user restarts AI Tavern Lite.
4. Before replacement, AI Tavern Lite creates a local `pre_restore_*` safety snapshot containing the current database and role assets.
5. The staged database and assets replace the current set before SQLAlchemy opens the database.
6. Alembic and schema validation run normally.
7. If startup fails, the pre-restore snapshot is restored automatically.
8. If startup succeeds, the staged files are removed and the local pre-restore safety snapshot is retained.

The local pre-restore safety snapshot may contain the current machine's API key because it is rollback material, not a portable backup. Keep the managed data directory private.

## Security limits

Restore rejects unsafe ZIP paths, duplicate paths, encrypted archives, symbolic links, unsupported asset types, oversized archives, unknown database tables, missing required columns, triggers, views, integrity failures, foreign-key failures, revision mismatches, and manifest/hash/count mismatches.
