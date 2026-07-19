# Frontend Request Race Fixes V1

This patch addresses only race conditions reproduced against the 05e8d93 baseline.

## Reproduced fixes

- A delayed session deletion no longer clears a session selected while deletion is pending.
- A delayed runtime save or rollback no longer writes into a different active session.
- A delayed stop request no longer clears a newer chat stream.
- Older settings reads and writes no longer overwrite a newer completed save.
- A delayed settings snapshot no longer replaces unsaved form edits.

## Existing protections retained

The baseline already prevented stale message, runtime, timeline, and SSE callbacks from replacing a newly selected session. It also already blocked duplicate synchronous sends. Those paths were verified but not redesigned.

## Scope

No backend APIs, database schema, API key storage, backup format, dependencies, or user data paths are changed.
