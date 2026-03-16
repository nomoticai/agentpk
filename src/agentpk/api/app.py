from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agentpk.api.routes import router


def create_app(ui: bool = True) -> FastAPI:
    app = FastAPI(
        title="agentpk API",
        description="REST API for packaging and certifying AI agents",
        version="1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],     # tighten in production
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    # Serve the packaging UI at /
    if ui:
        ui_dir = Path(__file__).parent / "ui"
        if ui_dir.exists():
            app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")

    return app
