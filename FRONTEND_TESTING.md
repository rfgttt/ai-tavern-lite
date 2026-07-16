# Frontend testing baseline

The frontend quality gate contains three layers:

- **API stream tests** validate SSE frame parsing, completion, and unexpected disconnect handling.
- **Store tests** validate character loading, character selection resets, session refresh, and persona/group bindings.
- **Component tests** validate the sidebar's character selection and new-chat guard behavior.

## Commands

Run once:

```bash
cd frontend
npm ci
npm run check
```

Watch during development:

```bash
npm test
```

Coverage report:

```bash
npm run test:coverage
```

`npm run check` is the frontend release gate. It runs test type checking, all Vitest tests, TypeScript production checking, and the Vite production build.

## Test layout

```text
tests/
  api/
  components/
  mocks/
  stores/
  setup.ts
  testUtils.tsx
```

MSW is the shared HTTP mock layer. Add endpoint handlers to `tests/mocks/handlers.ts` and reusable response objects to `tests/mocks/fixtures.ts`.
