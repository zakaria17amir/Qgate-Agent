"""Liveness, readiness and metrics endpoints shared by every service."""

import os
from collections.abc import Callable

import uvicorn
from fastapi import FastAPI, Response
from prometheus_client import make_asgi_app

Checks = Callable[[], dict[str, bool]]


def ok(probe: Callable[[], object]) -> bool:
    """True if ``probe()`` returns without raising — one dependency check."""
    try:
        probe()
        return True
    except Exception:
        return False


def health_app(service: str, ready: Checks | None = None) -> FastAPI:
    """``/health`` says the process is up; ``/ready`` runs ``ready()`` and is 503 unless every
    named dependency answers, so compose/k8s only route traffic to a service that can serve it."""
    app = FastAPI(title=service)
    app.mount("/metrics", make_asgi_app())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": service}

    @app.get("/ready")
    def readiness(response: Response) -> dict[str, bool]:
        checks = ready() if ready else {}
        if not all(checks.values()):
            response.status_code = 503
        return checks

    return app


def serve(app: FastAPI) -> None:
    """Run until interrupted. PORT comes from the environment (compose sets it)."""
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))  # noqa: S104
