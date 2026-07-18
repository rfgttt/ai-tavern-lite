from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import json

from .core.config import settings
from .core.logging import logger
from .db.session import SessionLocal, init_db
from .db.models import Character
from .api import create_api_router
from .services.runtime.turn_finalizer import recover_interrupted_generations
from .core.middleware import (
    BasicAuthMiddleware,
    InMemoryRateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)


def create_demo_character():
    """Create optional demo data only when explicitly enabled."""
    from .db.session import SessionLocal

    db = SessionLocal()
    try:
        count = db.query(Character).count()
        if count > 0:
            return

        # Create original demo character (no copyright issues)
        demo_char = {
            "spec": "chara_card_v3",
            "spec_version": "3.0",
            "data": {
                "name": "小酒馆招待·林夕",
                "description": "林夕是「星尘酒馆」的年轻招待，总是带着温和的微笑。她穿着简洁的侍者制服，长发束在脑后，眼睛里总带着好奇的光芒。她熟悉酒馆里每一位常客的故事，也喜欢倾听旅人们的见闻。",
                "personality": "温柔、耐心、善于倾听，偶尔有点调皮，喜欢给客人提一些有趣的建议。工作时认真负责，私下里也有活泼的一面。",
                "scenario": "你推开了「星尘酒馆」的木门，暖黄的灯光和淡淡的酒香扑面而来。此时正是傍晚，酒馆里还没有太多客人，林夕正在柜台后擦拭酒杯，看到你进来便微笑着打招呼。",
                "first_mes": "*林夕停下手中擦拭酒杯的动作，抬起头对你露出一个温和的微笑* 欢迎光临星尘酒馆。今天想喝点什么？还是说，你有故事想要分享？",
                "mes_example": "{{user}}: 这里有什么推荐的酒吗？\n{{char}}: *林夕歪头想了想，手指轻轻敲了敲柜台* 如果是第一次来的话，我推荐「星尘特调」——入口微甜，后味有点像仰望夜空的感觉。*她眨眨眼* 当然，如果你想听故事的话，我也可以免费讲一个。",
                "system_prompt": "",
                "post_history_instructions": "",
                "creator_notes": "AI Tavern Lite 演示角色",
                "creator": "AI Tavern Lite",
                "character_version": "1.0",
                "tags": ["演示", "酒馆", "日常"],
                "alternate_greetings": [
                    "*林夕正在整理桌上的菜单，听到脚步声抬起头* 啊，欢迎回来！老位置还是换个地方坐？",
                    "*林夕从后厨探出头，手里还拿着托盘* 稍等一下，我马上就来！今天新到了一批不错的茶叶哦。"
                ],
                "extensions": {},
                "character_book": {
                    "entries": [
                        {
                            "id": 1,
                            "keys": ["酒馆", "星尘"],
                            "secondary_keys": [],
                            "comment": "酒馆基本设定",
                            "content": "星尘酒馆是一座小镇边缘的小酒馆，以安静温馨的氛围著称。老板是一位神秘的老者，平时很少露面，日常都由林夕打理。酒馆提供酒水、简单餐点和热茶。",
                            "constant": True,
                            "selective": False,
                            "enabled": True,
                            "insertion_order": 0,
                            "position": "before_char",
                            "use_regex": False,
                            "probability": 100,
                            "extensions": {}
                        },
                        {
                            "id": 2,
                            "keys": ["猫", "猫咪", "小猫"],
                            "secondary_keys": [],
                            "comment": "酒馆的猫",
                            "content": "酒馆里养着一只叫「摩卡」的橘猫，很懒，总趴在靠窗的位置晒太阳。它是林夕捡回来的流浪猫，现在是酒馆的吉祥物。",
                            "constant": False,
                            "selective": False,
                            "enabled": True,
                            "insertion_order": 1,
                            "position": "before_char",
                            "use_regex": False,
                            "probability": 100,
                            "extensions": {}
                        }
                    ]
                }
            }
        }

        normalized_json = json.dumps(demo_char["data"], ensure_ascii=False)
        raw_json = json.dumps(demo_char, ensure_ascii=False)

        character = Character(
            name=demo_char["data"]["name"],
            description=demo_char["data"]["description"],
            personality=demo_char["data"]["personality"],
            scenario=demo_char["data"]["scenario"],
            first_message=demo_char["data"]["first_mes"],
            normalized_json=normalized_json,
            raw_json=raw_json,
            avatar_path=""
        )

        db.add(character)
        db.commit()
        logger.info("Demo character created: 小酒馆招待·林夕")

    finally:
        db.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings.validate_runtime_security()
    settings.ensure_directories()

    docs_enabled = not settings.is_production
    app = FastAPI(
        title="AI Tavern Lite",
        description="安全、可回滚的沉浸式角色卡运行平台",
        version="2.2.0-preview.1",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # Middleware is registered from inner to outer. Security headers and Host
    # validation stay outside authentication, while rate limiting runs before
    # Basic auth so repeated password attempts are also throttled.
    cors_origins = list(settings.cors_origin_items)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept"],
        )

    app.add_middleware(BasicAuthMiddleware)
    app.add_middleware(InMemoryRateLimitMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)

    allowed_hosts = list(settings.allowed_host_items)
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.add_middleware(SecurityHeadersMiddleware)

    # Initialize database. Production remains single-worker while SQLite and
    # in-process stream cancellation are in use.
    init_db()
    recovered = recover_interrupted_generations(SessionLocal)
    if recovered:
        logger.warning("Recovered %s interrupted generating messages", recovered)

    if settings.create_demo_data:
        logger.warning("Explicit demo-data creation is enabled")
        create_demo_character()

    app.include_router(
        create_api_router(
            include_diagnostics=settings.enable_diagnostics,
            include_selftest=settings.enable_selftest,
        )
    )

    avatar_dir = settings.avatars_dir
    avatar_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/avatars", StaticFiles(directory=str(avatar_dir)), name="avatars")

    frontend_dist = settings.frontend_dist_dir
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

        from fastapi.responses import FileResponse

        @app.get("/")
        async def serve_index():
            return FileResponse(str(frontend_dist / "index.html"))

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            blocked_production_paths = {"docs", "redoc", "openapi.json"}
            if (
                full_path.startswith("api/")
                or full_path.startswith("avatars/")
                or (
                    settings.is_production
                    and (
                        full_path in blocked_production_paths
                        or full_path.startswith("docs/")
                        or full_path.startswith("redoc/")
                    )
                )
            ):
                return JSONResponse(status_code=404, content={"detail": "Not Found"})
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return FileResponse(str(index_path))
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

        logger.info("Frontend static files mounted")
    else:
        logger.info("Frontend build not found, API only mode")

    logger.info(
        "AI Tavern Lite started environment=%s auth=%s diagnostics=%s selftest=%s",
        settings.environment,
        settings.auth_enabled,
        settings.enable_diagnostics,
        settings.enable_selftest,
    )
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False
    )
