"""Bearer-token auth for the api: HS256 JWTs carrying a role.

Dev-grade on purpose (shared secret, no OIDC — see design §12). Roles: ``viewer`` reads,
``approver`` decides at the gate, ``admin`` bumps baselines, ``service`` is the agent calling
``/internal/*``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class Role(StrEnum):
    VIEWER = "viewer"
    APPROVER = "approver"
    ADMIN = "admin"
    SERVICE = "service"


@dataclass(frozen=True)
class Principal:
    sub: str
    role: Role


def mint(sub: str, role: Role, secret: str, ttl: timedelta = timedelta(hours=8)) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": sub, "role": role.value, "iat": now, "exp": now + ttl}, secret, "HS256"
    )


def verify(token: str, secret: str) -> Principal:
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"invalid token: {e}") from e
    return Principal(sub=str(claims["sub"]), role=Role(claims["role"]))


_bearer = HTTPBearer(auto_error=False)


def require(*roles: Role, secret: str) -> Callable[..., Principal]:
    """FastAPI dependency: a valid token whose role is one of ``roles``."""

    def dependency(
        creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> Principal:
        if creds is None:
            raise HTTPException(401, "missing bearer token")
        principal = verify(creds.credentials, secret)
        if principal.role not in roles:
            raise HTTPException(403, f"role {principal.role} may not do this")
        return principal

    return dependency
