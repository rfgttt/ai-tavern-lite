# AI Tavern 2.0 Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a runnable 2.0 preview with persistent chat workspace, generic card runtime, structured message rendering, compatibility reporting, prompt budgeting, Persona/group/branch foundations, and safe declarative extensions.

**Architecture:** Preserve raw V2/V3 cards through adapter analysis, store generic runtime and message render artifacts separately from prose, and keep the chat workspace mounted while settings/memory open as overlays. Unknown card variables render through a generic inspector, while declared UI manifests map state paths to native components; arbitrary card JavaScript remains disabled.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy, SQLite, React 18, TypeScript, Zustand, Tailwind CSS.

## Global Constraints

- Existing 1.2 databases must migrate idempotently.
- Never execute card-provided JavaScript in the application origin.
- Unknown extensions and runtime variables must be retained rather than discarded.
- Returning from settings must not clear messages or restart historical animations.
- Recent chat history must retain a guaranteed minimum budget ahead of optional lorebook content.
- The release ZIP must not include databases, API keys, logs, virtual environments, node_modules, or imported cards.

---

### Task 1: Card adapters and compatibility report

**Files:**
- Create: `backend/app/services/cards/compatibility.py`
- Modify: `backend/app/services/character_parser/parser.py`
- Modify: `backend/app/api/characters.py`
- Modify: `backend/app/schemas/__init__.py`
- Test: `backend/tests/test_card_compatibility.py`

- [ ] Add failing tests for V2/V3, MVU, regex, assets, UI manifest, unknown extensions, and disabled-entry exclusion.
- [ ] Implement canonical capability analysis and compatibility API.
- [ ] Verify focused tests pass.

### Task 2: Message AST and render artifacts

**Files:**
- Create: `backend/app/services/rendering/message_ast.py`
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/db/session.py`
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/api/sessions.py`
- Modify: `backend/app/api/chat.py`
- Test: `backend/tests/test_message_ast.py`

- [ ] Add failing tests for narration, named dialogue, thoughts, actions, stable speaker metadata, and legacy message migration.
- [ ] Add message render columns and idempotent migrations.
- [ ] Parse and persist segments/artifacts on completed assistant turns and API reads.
- [ ] Verify focused tests pass.

### Task 3: Prompt planner and World Info budget

**Files:**
- Create: `backend/app/services/prompt_builder/planner.py`
- Modify: `backend/app/services/prompt_builder/builder.py`
- Modify: `backend/app/services/lorebook/service.py`
- Test: `backend/tests/test_prompt_planner.py`

- [ ] Add failing tests guaranteeing recent turns and limiting lorebook budget.
- [ ] Implement section budgets, lore ranking, and diagnostics metadata.
- [ ] Verify focused and chat-flow tests pass.

### Task 4: Persona, group, and branch foundations

**Files:**
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/db/session.py`
- Modify: `backend/app/schemas/__init__.py`
- Create: `backend/app/api/personas.py`
- Create: `backend/app/api/groups.py`
- Create: `backend/app/api/branches.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_2x_foundations.py`

- [ ] Add failing CRUD tests for personas, group members, and branch snapshots.
- [ ] Implement idempotent tables and APIs.
- [ ] Verify focused tests pass.

### Task 5: Persistent workspace and cached sessions

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/stores/appStore.ts`
- Modify: `frontend/src/pages/ChatPage.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/pages/MemoryPage.tsx`

- [ ] Keep ChatWorkspace mounted and render settings/memory as overlays.
- [ ] Add per-session cache, request generations, background refresh, scroll/draft persistence, and explicit errors.
- [ ] Build frontend and fix type regressions.

### Task 6: Generic runtime renderer and colored dialogue

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/index.ts`
- Create: `frontend/src/components/messages/StructuredMessage.tsx`
- Create: `frontend/src/components/runtime/GenericDataPanel.tsx`
- Create: `frontend/src/components/runtime/CardCompatibilityPanel.tsx`
- Create: `frontend/src/components/runtime/ManifestPanel.tsx`
- Modify: `frontend/src/components/ChatView.tsx`
- Modify: `frontend/src/components/runtime/RuntimePanel.tsx`
- Modify: `frontend/src/components/CharacterPanel.tsx`
- Modify: `frontend/src/index.css`

- [ ] Render persisted AST with stable speaker colors and distinct narration/actions.
- [ ] Render unknown runtime values recursively and declared native manifest panels.
- [ ] Display compatibility report and unsupported capabilities.
- [ ] Build frontend and inspect representative cards.

### Task 7: 2.0 navigation and foundations UI

**Files:**
- Create: `frontend/src/components/PersonaManager.tsx`
- Create: `frontend/src/components/GroupManager.tsx`
- Create: `frontend/src/components/BranchManager.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/api/index.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] Add basic Persona CRUD, group composition, and branch save/restore UI.
- [ ] Keep controls compact and non-blocking.
- [ ] Build frontend.

### Task 8: Release verification

**Files:**
- Modify: `README.md`
- Create: `AI_TAVERN_2_PREVIEW.md`
- Modify: `frontend/package.json`
- Modify: `backend/app/schemas/__init__.py`

- [ ] Run full backend tests.
- [ ] Run frontend production build and npm audit.
- [ ] Smoke-test health, compatibility, Persona/group/branch, chat restoration, and diagnostics export.
- [ ] Create sanitized release ZIP and verify from a fresh extraction.
