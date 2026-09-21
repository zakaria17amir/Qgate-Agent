"""Foreign plant system: deliberately shares no code with qgate-core."""

import os

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="mock-mes")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mock-mes"}


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8003")))  # noqa: S104
