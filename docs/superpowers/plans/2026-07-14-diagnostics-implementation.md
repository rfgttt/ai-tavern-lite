# Diagnostics System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe structured diagnostics, health checks, and one-click ZIP export to AI Tavern.

**Architecture:** A backend `DiagnosticService` owns log storage, redaction, health data, request summaries, and ZIP generation. Chat streaming reports lifecycle metrics to it, while a new diagnostics router exposes read/export/clear actions; the settings page consumes those APIs.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy, standard-library logging/zipfile/platform; React 18, TypeScript, Axios.

## Global Constraints

- Never write full API keys, authorization headers, custom header values, full prompts, card content, or chat bodies to diagnostics.
- Diagnostic failures must never fail a chat request.
- Logs rotate at 10 MB with 5 backups; daily chat logs older than 7 days are removed.
- ZIP export must be usable on Windows through the browser.

---

### Task 1: Diagnostic storage and redaction

**Files:**
- Create: `backend/app/services/diagnostics/service.py`
- Create: `backend/app/services/diagnostics/__init__.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/logging.py`
- Test: `backend/tests/test_diagnostics_service.py`

- [ ] Write failing tests for API-key, URL, nested mapping, and exception redaction.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Implement directory setup, rotating logs, JSONL request records, latest request persistence, cleanup, and redaction.
- [ ] Run focused tests and confirm they pass.

### Task 2: Health and export API

**Files:**
- Create: `backend/app/api/diagnostics.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_diagnostics_api.py`

- [ ] Write failing API tests for health, latest request, ZIP export, and clear logs.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement health checks, database summary, sanitized settings, ZIP response, and log clearing.
- [ ] Run focused tests and confirm they pass.

### Task 3: Chat request instrumentation

**Files:**
- Modify: `backend/app/api/chat.py`
- Test: `backend/tests/test_diagnostics_chat.py`

- [ ] Write failing tests for complete, stopped, and error request summaries.
- [ ] Run focused tests and confirm expected failures.
- [ ] Add request IDs, timing/chunk counters, prompt metadata, state results, and safe completion recording.
- [ ] Run focused tests and confirm they pass.

### Task 4: Frontend diagnostics panel

**Files:**
- Modify: `frontend/src/api/index.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] Add typed health/latest/export/clear API clients.
- [ ] Add health state, refresh/export/clear handlers, and browser ZIP download.
- [ ] Render diagnostic health cards and latest request details.
- [ ] Run TypeScript and production build.

### Task 5: Documentation and release verification

**Files:**
- Modify: `README.md`
- Create: `DIAGNOSTICS.md`

- [ ] Document health checks, exported ZIP contents, privacy guarantees, and how to share diagnostics.
- [ ] Run full backend tests.
- [ ] Run frontend `npm ci`, audit, and production build.
- [ ] Create a sanitized release ZIP and verify it from a fresh extraction.
