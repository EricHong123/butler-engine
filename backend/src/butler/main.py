"""FastAPI application factory for Butler Engine."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from butler.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # Startup
    settings.data_root.mkdir(parents=True, exist_ok=True)

    # Init database (create tables if not exist)
    try:
        from butler.services.database import init_db, close_db
        await init_db()
    except Exception:
        pass  # DB not available — run without it

    yield

    # Shutdown
    try:
        from butler.services.database import close_db
        await close_db()
    except Exception:
        pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Butler Engine",
        version="0.1.0",
        description="High-Net-Worth Private AI Butler — Core Agent Engine",
        lifespan=lifespan,
    )

    # Rate limiting middleware (applied to all /api routes)
    from butler.api.middleware import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)

    from butler.wechat.webhook import router as wechat_router
    app.include_router(wechat_router)

    from butler.review.router import router as review_router
    app.include_router(review_router)

    from butler.api.router_conversation import router as conv_router
    app.include_router(conv_router)

    from butler.api.router_dashboard import router as dashboard_router
    app.include_router(dashboard_router)

    from butler.api.router_auth import router as auth_router
    app.include_router(auth_router)

    from butler.api.router_wechat_setup import router as wechat_setup_router
    app.include_router(wechat_setup_router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "app": settings.app_name}

    @app.get("/api/rate-limit-status")
    async def rate_limit_status(tenant_id: str = "demo-001"):
        from butler.api.middleware import get_rate_limit_status
        return get_rate_limit_status(tenant_id)

    return app


app = create_app()
