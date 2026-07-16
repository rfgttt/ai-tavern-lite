# P0 production security fixes

## Implemented

- Production startup refuses `auth_mode=none`.
- Single-user Bearer-token mode and trusted access-proxy mode.
- Frontend stores the access token locally and retries API requests after a 401 prompt.
- Health endpoint remains public for container health checks.
- Diagnostics and self-test routes are not registered in production.
- Swagger, ReDoc and OpenAPI endpoints are disabled in production.
- SSRF validation for model Base URLs:
  - HTTPS only in production.
  - Rejects credentials in URLs.
  - Rejects localhost, `.local`, private, loopback, link-local, reserved and metadata-style targets.
  - Resolves DNS and validates every returned address.
  - Supports an exact-host allowlist.
- Arbitrary custom model headers are rejected in production settings updates.
- Per-client in-memory request limiting for the current single-worker architecture.
- Maximum request-body size check.
- Trusted-host validation, explicit CORS origins and standard security headers.
- SPA fallback now returns a real HTTP 404 for missing API paths.
- Multi-stage Dockerfile, non-root runtime, one worker, health check and persistent volume example.
- Runtime databases, backups, logs, diagnostics, self-test archives and dependency/build folders removed from the release copy.
- `.dockerignore`, expanded `.gitignore`, production environment example and Compose configuration added.

## Deployment notes

1. Delete or rotate the old model API key yourself as planned.
2. Copy `.env.production.example` to `.env` and generate a random access token.
3. Set the real public hostname in `AI_TAVERN_ALLOWED_HOSTS`.
4. Set the exact browser origin in `AI_TAVERN_ALLOWED_ORIGINS`.
5. Prefer setting `AI_TAVERN_OUTBOUND_HOST_ALLOWLIST` to the exact model API hostname(s).
6. Run behind an HTTPS reverse proxy. The Compose port binds to localhost only.
7. Keep one application worker and one replica while using SQLite and process-local generation cancellation.

## Verification

- Backend: 132 tests passed.
- Frontend: TypeScript and Vite production build passed.
