# Tavern-Compatible Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a card-driven right rail and explicit session management without breaking existing databases, streaming persistence, branches, or diagnostics.

**Architecture:** Preserve the existing safe canonical runtime and snapshot model. Add normalization and display-classification helpers, then replace fixed frontend panels with conditional card-driven components. Keep technical details behind an expandable developer section.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React 18, TypeScript, Zustand, Axios, Tailwind/CSS, pytest.

## Global Constraints

- Do not execute arbitrary card JavaScript.
- Preserve existing database compatibility.
- Do not display invented scene, relationship, task, or environment values as real data.
- Preserve streaming persistence and branch snapshot hotfixes.
- No new frontend runtime dependency unless unavoidable.

---

### Task 1: Runtime normalization and capability semantics

**Files:**
- Modify: `backend/app/services/runtime/output_parser.py`
- Modify: `backend/app/services/runtime/card_profile.py`
- Modify: `backend/app/services/runtime/prompt.py`
- Test: `backend/tests/test_runtime_output_parser.py`
- Test: `backend/tests/test_runtime_profile.py`

- [ ] Add failing tests for Chinese/English state aliases and card-driven relationship capability.
- [ ] Verify tests fail for missing alias mapping and capability semantics.
- [ ] Implement alias normalization and prompt language that avoids invented scores.
- [ ] Run focused tests and full runtime tests.

### Task 2: Lorebook and compatibility detail

**Files:**
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/services/cards/compatibility.py`
- Modify: `frontend/src/components/runtime/CardCompatibilityPanel.tsx`
- Modify: `frontend/src/types/index.ts`
- Test: `backend/tests/test_card_compatibility.py`
- Test: `backend/tests/test_immersive_chat_flow.py`

- [ ] Add failing tests for human-readable capability details and complete lore metadata.
- [ ] Implement capability status records and lore preview/source fields.
- [ ] Render translated conclusions rather than raw capability keys.
- [ ] Run focused tests.

### Task 3: Explicit session menu

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/stores/appStore.ts`
- Modify: `frontend/src/api/index.ts`
- Modify: `frontend/src/index.css`

- [ ] Add store actions for rename, delete, and export.
- [ ] Add per-session menu with confirmation and current-session cleanup.
- [ ] Build frontend to catch type and UI integration errors.

### Task 4: Conditional runtime rail

**Files:**
- Create: `frontend/src/components/runtime/runtimePresentation.ts`
- Create: `frontend/src/components/runtime/SceneStatus.tsx`
- Create: `frontend/src/components/runtime/CardStateSections.tsx`
- Create: `frontend/src/components/runtime/LorebookActivity.tsx`
- Modify: `frontend/src/components/runtime/RuntimePanel.tsx`
- Modify: `frontend/src/components/runtime/RelationshipStatus.tsx`
- Modify: `frontend/src/components/runtime/EventTimeline.tsx`
- Modify: `frontend/src/components/runtime/GenericDataPanel.tsx`
- Modify: `frontend/src/index.css`

- [ ] Implement pure classification/recency helpers.
- [ ] Remove fake fallbacks and hide unchanged default panels.
- [ ] Render real card-native categories and developer-only raw state.
- [ ] Rename and explain timeline; enrich lore entries.
- [ ] Build frontend.

### Task 5: Regression and release packaging

**Files:**
- Modify: `scripts/self_test_runner.py`
- Modify: `SELF_TEST.md`
- Create: `RELEASE_NOTES_2.1.md`

- [ ] Extend self-test report markers for session controls and card-driven panel behavior.
- [ ] Run the complete backend suite.
- [ ] Run frontend production build and npm audit.
- [ ] Start an isolated server and verify health, Mock chat, runtime, timeline, session delete, and diagnostics export.
- [ ] Create a clean ZIP without database, logs, `.venv`, or `node_modules`.
- [ ] Re-extract the final ZIP and repeat tests/build.
