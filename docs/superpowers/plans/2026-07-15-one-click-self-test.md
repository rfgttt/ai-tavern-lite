# One-Click Self-Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a one-click Windows self-test and exportable diagnostic report.

**Architecture:** A local Python orchestrator runs API tests and coordinates a same-origin React self-test page. A file-backed backend service aggregates redacted backend/frontend results and creates a combined ZIP.

**Tech Stack:** Python 3.10+, FastAPI, httpx, React 18, TypeScript, Zustand, Vite.

## Global Constraints

- No Playwright, Selenium, browser driver, or extra Python dependency.
- Never export full API keys, prompts, chat bodies, or role-card contents.
- Always export a report even when tests fail.
- Delete temporary application test data after the run.

---

### Task 1: Self-test report service and API
- [ ] Add failing API tests for run creation, component result submission, status retrieval, and ZIP export.
- [ ] Implement file-backed run service with redaction and expiry cleanup.
- [ ] Add API routes and register the router.
- [ ] Run focused and full backend tests.

### Task 2: Browser self-test page
- [ ] Add a self-test API client and TypeScript result types.
- [ ] Add stable `data-testid` markers and a query-gated application test hook.
- [ ] Add `/self-test` page with iframe session-return checks and component rendering checks.
- [ ] Build the production frontend.

### Task 3: One-click Windows runner
- [ ] Implement the Python orchestrator and SSE parser.
- [ ] Add `run-self-test.bat` and PowerShell fallback launcher.
- [ ] Ensure Mock mode restoration and generated-data cleanup.
- [ ] Ensure failed runs still create an export ZIP.

### Task 4: End-to-end verification and release
- [ ] Run backend tests, frontend build, and npm audit.
- [ ] Run the self-test against a fresh database and inspect the exported ZIP.
- [ ] Package a clean release without database, `.venv`, `node_modules`, or logs.
