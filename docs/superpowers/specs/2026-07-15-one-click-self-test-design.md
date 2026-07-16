# AI Tavern One-Click Self-Test Design

## Goal

Provide a Windows-friendly one-click self-test that starts or reuses AI Tavern, runs backend/API/SSE/state/branch tests, opens a same-origin browser test page for real frontend checks, and exports one ZIP the user can upload for diagnosis.

## Architecture

- `run-self-test.bat` invokes the existing backend virtual environment.
- `scripts/self_test_runner.py` starts the service if needed, creates isolated temporary test data, runs API tests, opens `/self-test`, waits for browser results, cleans test data, and downloads the final ZIP.
- `/api/self-test/runs/*` stores redacted run reports as short-lived JSON files and exports them together with the existing diagnostics bundle.
- `/self-test` runs actual React component and iframe checks without Playwright or browser drivers.

## Test Coverage

Backend: health, static frontend, card import/compatibility, Persona, group, session, SSE completion, message persistence, runtime patch, prompt preview, branch save/restore, latest diagnostics, diagnostics ZIP.

Frontend: application iframe load, session cache restore, settings overlay preserving ChatPage, draft and scroll preservation, loading state, stable distinct speaker colors, generic dynamic data rendering.

## Safety

The runner temporarily enables Mock mode but restores the original Mock setting. It never reads or exports a complete API key, prompt, chat body, or user role card. All generated character/session/persona/group data are deleted after the run. Reports are redacted through the diagnostics sanitizer.

## Success Criteria

A run exports a ZIP even when some tests fail. The summary identifies each test, duration, status, and error. Critical failures cause a non-zero process exit code but do not prevent report export.
