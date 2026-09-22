from datetime import timedelta
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from qgate_core.auth import Principal, Role, mint, require

pytestmark = pytest.mark.unit
SECRET = "unit-test-secret"


approver_or_admin = require(Role.APPROVER, Role.ADMIN, secret=SECRET)


def app() -> TestClient:
    a = FastAPI()

    @a.get("/decide")
    def decide(p: Annotated[Principal, Depends(approver_or_admin)]) -> dict[str, str]:
        return {"sub": p.sub, "role": p.role}

    return TestClient(a)


def bearer(role: Role, ttl: timedelta = timedelta(hours=1)) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint('alice', role, SECRET, ttl)}"}


def test_approver_is_admitted_and_identified() -> None:
    assert app().get("/decide", headers=bearer(Role.APPROVER)).json() == {
        "sub": "alice",
        "role": "approver",
    }


def test_viewer_is_forbidden() -> None:
    assert app().get("/decide", headers=bearer(Role.VIEWER)).status_code == 403


def test_missing_or_expired_token_is_unauthorized() -> None:
    c = app()
    assert c.get("/decide").status_code == 401
    assert c.get("/decide", headers=bearer(Role.APPROVER, timedelta(seconds=-5))).status_code == 401
    assert c.get("/decide", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
