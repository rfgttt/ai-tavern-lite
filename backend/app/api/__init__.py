from fastapi import APIRouter

from . import backups, branches, characters, chat, diagnostics, groups, health, memory, personas, runtime, selftest, sessions, settings, state_aliases


def create_api_router(*, include_diagnostics: bool = True, include_selftest: bool = True) -> APIRouter:
    api_router = APIRouter(prefix="/api")
    api_router.include_router(health.router)
    api_router.include_router(characters.router)
    api_router.include_router(state_aliases.router)
    api_router.include_router(sessions.router)
    api_router.include_router(chat.router)
    api_router.include_router(settings.router)
    api_router.include_router(memory.router)
    api_router.include_router(runtime.router)
    api_router.include_router(personas.router)
    api_router.include_router(groups.router)
    api_router.include_router(branches.router)
    api_router.include_router(backups.router)
    if include_diagnostics:
        api_router.include_router(diagnostics.router)
    if include_selftest:
        api_router.include_router(selftest.router)
    return api_router


# Backwards-compatible router for tests and local imports.
api_router = create_api_router()
