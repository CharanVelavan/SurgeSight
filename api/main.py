"""SurgeSight API (WP9): thin FastAPI wrappers over the services. Run with ``uvicorn api.main:app``."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.ratelimit import RateLimitMiddleware
from api.routes_analysis import router as analysis_router
from api.routes_ops import router as ops_router
from api.routes_push import router as push_router
from api.routes_web import router as web_router
from services.config import get_settings

DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def create_app() -> FastAPI:
    app = FastAPI(title="SurgeSight API", version="0.1.0",
                  description="Cyclone impact screening for disaster-management officers. Screening indices, not damage probabilities; not an official warning service.")
    origins = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(analysis_router)
    app.include_router(ops_router)
    app.include_router(push_router)
    app.include_router(web_router)

    @app.get("/healthz")
    def health() -> dict[str, str]:
        settings = get_settings()
        return {"status": "ok", "env": settings.env, "store": settings.store, "dispatch_mode": settings.dispatch_mode}

    return app


app = create_app()
