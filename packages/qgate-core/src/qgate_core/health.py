"""Liveness and metrics endpoints shared by every service."""

import os

import uvicorn
from fastapi import FastAPI
from prometheus_client import make_asgi_app


def health_app(service: str) -> FastAPI:
    app = FastAPI(title=service)
    app.mount("/metrics", make_asgi_app())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": service}

    return app


def serve(app: FastAPI) -> None:
    """Run until interrupted. PORT comes from the environment (compose sets it)."""
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))  # noqa: S104
