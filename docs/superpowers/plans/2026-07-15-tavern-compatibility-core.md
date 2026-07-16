# Tavern Compatibility Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic SillyTavern-compatible runtime layer for MVU initialization, safe macros, variable path mapping, native status placeholders, and runtime-level compatibility reporting.

**Architecture:** Introduce focused compatibility services rather than per-card branches. Card import/profile analysis produces a compatibility manifest; session initialization consumes safe variable sources; prompt construction resolves an allow-listed macro subset; output parsing normalizes all unknown card paths into `/custom`; rendering converts status placeholders into native artifacts while arbitrary JavaScript remains disabled.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, React 18, TypeScript, Vite, pytest.

## Global Constraints

- Do not execute card-provided JavaScript, EJS, HTML event handlers, external scripts, or arbitrary STscript.
- Do not add a card-name check or any logic specific to 雾叶泠.
- Preserve unknown card extensions and original card data.
- Do not add a new Python dependency for YAML parsing.
- Existing databases and saved sessions must remain readable.
- Unknown top-level card variables must live under `/custom`.

---

### Task 1: Safe variable initialization

**Files:**
- Create: `backend/app/services/tavern_compat/__init__.py`
- Create: `backend/app/services/tavern_compat/initial_state.py`
- Test: `backend/tests/test_tavern_compat_initial_state.py`

**Interfaces:**
- Produces: `extract_card_variables(normalized: dict) -> InitialVariableResult`
- Produces: `merge_card_variables(base_state: dict, variables: dict) -> dict`

- [ ] Write failing tests for Tavern Helper `variables.stat_data`, disabled `[initvar]` YAML subset, nested objects, numeric/boolean scalars, and unrelated disabled entries.
- [ ] Run the focused test and verify failure because the module does not exist.
- [ ] Implement a safe indentation-based YAML subset parser and prioritized variable extraction.
- [ ] Run the focused test and verify all cases pass.

### Task 2: Generic MVU path normalization

**Files:**
- Create: `backend/app/services/tavern_compat/paths.py`
- Modify: `backend/app/services/runtime/output_parser.py`
- Test: `backend/tests/test_tavern_compat_paths.py`

**Interfaces:**
- Produces: `normalize_card_pointer(path: str) -> str`

- [ ] Write failing tests for canonical roots, `/stat_data/...`, `/variables/...`, arbitrary Unicode roots, `/custom/...`, and JSON Pointer escaping.
- [ ] Verify the focused test fails against current behavior.
- [ ] Implement one normalizer and use it for JSONPatch `path` and `from`.
- [ ] Verify focused tests and existing runtime parser tests pass.

### Task 3: Session initialization integration

**Files:**
- Modify: `backend/app/services/runtime/state_engine.py`
- Modify: `backend/app/services/runtime/session_service.py`
- Test: `backend/tests/test_tavern_compat_session.py`

**Interfaces:**
- Consumes: `extract_card_variables`, `merge_card_variables`
- Produces: initialized `SessionState.initial_state_json` and `state_json`

- [ ] Write a failing session test proving a disabled `[initvar]` entry initializes custom variables and accepts a later `replace` patch.
- [ ] Verify failure shows missing path.
- [ ] Merge extracted variables into the initial state without overriding platform roots.
- [ ] Verify the focused test and state-engine tests pass.

### Task 4: Safe macro compatibility

**Files:**
- Create: `backend/app/services/tavern_compat/macros.py`
- Modify: `backend/app/services/character_parser/parser.py`
- Modify: `backend/app/services/prompt_builder/builder.py`
- Modify: `backend/app/services/lorebook/service.py`
- Test: `backend/tests/test_tavern_compat_macros.py`

**Interfaces:**
- Produces: `MacroContext`
- Produces: `resolve_safe_macros(text: str, context: MacroContext) -> str`

- [ ] Write failing tests for `{{user}}`, `<user>`, `{{char}}`, `<char>`, `{{getvar::stat_data.path}}`, and `{{format_message_variable::stat_data}}`.
- [ ] Verify failure against current replacement behavior.
- [ ] Implement allow-listed read-only macro resolution; unknown macros remain visible and are reported, never executed.
- [ ] Apply resolver to character fields, history, user input, and selected lorebook content.
- [ ] Verify prompt and parser regression tests pass.

### Task 5: Native status placeholder rendering

**Files:**
- Modify: `backend/app/services/rendering/message_ast.py`
- Modify: `backend/app/api/sessions.py`
- Modify: `backend/app/services/runtime/turn_finalizer.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/messages/StructuredMessage.tsx`
- Create: `frontend/src/components/messages/InlineCardState.tsx`
- Test: `backend/tests/test_tavern_compat_status_placeholder.py`

**Interfaces:**
- Produces AST segment `{type: "card-state-placeholder"}`.

- [ ] Write a failing AST test proving `<StatusPlaceHolderImpl/>` is removed from Markdown and represented as a native segment.
- [ ] Verify the focused test fails.
- [ ] Parse placeholders in first messages and final replies; persist AST for first messages.
- [ ] Render an inline safe state summary from current runtime state, with no HTML or script execution.
- [ ] Run backend tests and frontend production build.

### Task 6: Runtime compatibility report

**Files:**
- Modify: `backend/app/services/cards/compatibility.py`
- Modify: `backend/app/services/runtime/card_profile.py`
- Modify: `frontend/src/components/runtime/CardCompatibilityPanel.tsx`
- Test: `backend/tests/test_tavern_compat_report.py`

**Interfaces:**
- Produces report version 3 with `runtime_checks` and capability statuses.

- [ ] Write failing tests distinguishing protocol detection from usable initialization and patch paths.
- [ ] Verify current report incorrectly marks the card fully supported.
- [ ] Add checks for initial variables, supported read-only macros, unsupported dynamic EJS/STscript, placeholder conversion, and external JavaScript isolation.
- [ ] Update frontend wording to show supported/partial/blocked reasons.
- [ ] Run focused tests and frontend build.

### Task 7: Cross-card acceptance and packaging

**Files:**
- Create: `backend/tests/fixtures/tavern_helper_mvu_card.json`
- Create: `backend/tests/fixtures/generic_mvu_card.json`
- Modify: `scripts/self_test_runner.py`
- Modify: `RELEASE_NOTES_2.2_PREVIEW.md`

**Interfaces:**
- Acceptance covers two structurally different cards with the same runtime code.

- [ ] Add acceptance tests for the uploaded card shape and a distinct English generic MVU card.
- [ ] Run full backend test suite.
- [ ] Run frontend clean install/build and npm audit.
- [ ] Run isolated API smoke test: import card, create session, inspect initialized state, finalize a patch, read timeline and compatibility report.
- [ ] Build a full ZIP and an upgrade patch without data, `.venv`, `node_modules`, secrets, or internal registry URLs.
- [ ] Re-extract final ZIP and repeat tests/build/smoke checks.
