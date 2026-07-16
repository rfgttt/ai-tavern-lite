# Immersive Character Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe, persistent, reversible immersive runtime with card capability analysis, structured state updates, native RPG/relationship panels, dice, battle snapshots, choices, events, and lorebook visibility.

**Architecture:** A backend runtime layer analyzes cards, initializes per-session JSON state, parses hidden model metadata and recognized legacy text blocks, validates patches, and stores a snapshot per assistant turn. The frontend consumes runtime APIs and SSE metadata to render native components; arbitrary card scripts and replacement HTML remain inert.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, SQLite, React 18, TypeScript, Zustand, Tailwind CSS.

## Global Constraints

- Do not analyze or adapt disabled worldbook entries.
- Do not execute card-provided HTML, JavaScript, regex replacement HTML, or remote iframes.
- Preserve V2/V3 raw and normalized card data for export compatibility.
- All state mutations must be validated and reversible.
- Existing chat, settings, memory, and import tests must continue to pass.

---

### Task 1: Runtime profile and state defaults

**Files:**
- Create: `backend/app/services/runtime/card_profile.py`
- Create: `backend/app/services/runtime/state_engine.py`
- Create: `backend/app/services/runtime/__init__.py`
- Modify: `backend/app/services/character_parser/parser.py`
- Test: `backend/tests/test_runtime_profile.py`

**Interfaces:**
- Produces `analyze_card(normalized: dict) -> dict`
- Produces `build_initial_state(profile: dict, normalized: dict) -> dict`
- Produces `apply_patch(state: dict, operations: list[dict]) -> PatchResult`

- [ ] Write failing tests for D&D capability recognition, general-card defaults, and safe patch validation.
- [ ] Run targeted tests and confirm expected failures.
- [ ] Implement runtime profile, default state, JSON pointer helpers, clamps, and state-size limits.
- [ ] Run targeted tests and the existing parser tests.

### Task 2: Persistence and runtime API

**Files:**
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/db/session.py`
- Modify: `backend/app/schemas/__init__.py`
- Create: `backend/app/api/runtime.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/api/sessions.py`
- Test: `backend/tests/test_runtime_api.py`

**Interfaces:**
- Adds `SessionState` and `TurnSnapshot` models.
- Produces `RuntimeSessionResponse`, `RuntimeTimelineItem`, and rollback APIs.

- [ ] Write failing API tests for session initialization, runtime retrieval, timeline, state update, and rollback.
- [ ] Run targeted tests and confirm failures.
- [ ] Add tables, relationships, idempotent migration indexes, runtime endpoints, and session initialization.
- [ ] Run targeted tests and data-integrity tests.

### Task 3: Structured output parser and prompt injection

**Files:**
- Create: `backend/app/services/runtime/output_parser.py`
- Modify: `backend/app/services/prompt_builder/builder.py`
- Test: `backend/tests/test_runtime_output_parser.py`

**Interfaces:**
- Produces `parse_runtime_output(text: str) -> ParsedRuntimeOutput`.
- Produces `build_runtime_prompt(profile: dict, state: dict) -> str`.

- [ ] Write failing tests for native state blocks, MVU JSONPatch, dice, battlecheck, battle maps, malformed metadata, and visible narrative cleanup.
- [ ] Run targeted tests and confirm failures.
- [ ] Implement parsers and runtime prompt generation.
- [ ] Run targeted tests and prompt tests.

### Task 4: Chat integration and state-safe regeneration

**Files:**
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/api/sessions.py`
- Test: `backend/tests/test_immersive_chat_flow.py`

**Interfaces:**
- SSE `runtime` and enriched `done` events.
- Turn snapshots tied to assistant message IDs.

- [ ] Write failing tests for parsed visible content, patch persistence, lorebook metadata, stopped/error turns, and regenerate rollback.
- [ ] Run targeted tests and confirm failures.
- [ ] Integrate state prompt, stream-safe metadata buffering, snapshot writes, and rollback before regeneration.
- [ ] Run chat-flow and full backend tests.

### Task 5: Frontend runtime types, API, and store

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/index.ts`
- Modify: `frontend/src/stores/appStore.ts`

**Interfaces:**
- Adds `RuntimeState`, `RuntimeProfile`, `TurnRuntime`, `DiceResult`, `BattleSnapshot`.
- Store loads runtime on session selection and updates it from SSE events.

- [ ] Add runtime TypeScript types.
- [ ] Add API methods and extended SSE handlers.
- [ ] Add Zustand runtime state, loading, choice sending, and rollback actions.
- [ ] Run TypeScript build to expose integration errors.

### Task 6: Native immersive components

**Files:**
- Create: `frontend/src/components/runtime/RuntimePanel.tsx`
- Create: `frontend/src/components/runtime/RelationshipStatus.tsx`
- Create: `frontend/src/components/runtime/RpgStatus.tsx`
- Create: `frontend/src/components/runtime/DiceCard.tsx`
- Create: `frontend/src/components/runtime/BattleCheckCard.tsx`
- Create: `frontend/src/components/runtime/BattleMap.tsx`
- Create: `frontend/src/components/runtime/ChoiceBar.tsx`
- Create: `frontend/src/components/runtime/EventTimeline.tsx`
- Create: `frontend/src/components/runtime/RuntimeMessageMeta.tsx`
- Modify: `frontend/src/components/ChatView.tsx`
- Modify: `frontend/src/pages/ChatPage.tsx`
- Replace: `frontend/src/components/CharacterPanel.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Renders only structured runtime data and sanitized markdown.
- Supports desktop side panel and mobile drawer.

- [ ] Replace all fake panel data with runtime data.
- [ ] Add native dice, battle check, tactical snapshot, event, and choice components.
- [ ] Add rollback controls and mobile runtime drawer.
- [ ] Run production build and manually inspect mock-mode stage.

### Task 7: Documentation, fixtures, and release verification

**Files:**
- Create: `backend/tests/fixtures/dnd_runtime_fixture.json`
- Modify: `README.md`
- Create: `IMMERSIVE_RUNTIME.md`
- Modify: `REPAIR_NOTES.md`

**Interfaces:**
- Documents supported card conventions and explicit non-support for executing scripts.

- [ ] Add a minimal non-adult D&D fixture containing only state, dice, and battle conventions.
- [ ] Document runtime protocol, APIs, compatibility, safety, and rollback.
- [ ] Run full backend tests, frontend build, npm audit, and a mock-mode end-to-end smoke test.
- [ ] Remove databases, caches, node_modules, and build output from the release archive.
