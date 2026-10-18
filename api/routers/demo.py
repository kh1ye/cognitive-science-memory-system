"""Opt-in, authenticated endpoints for destructive demo initialization."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..dependencies import MemoryDependency
from ..schemas import NamespaceRequest
from ..seed import seed_demo

bearer = HTTPBearer(auto_error=False)


def require_demo_access(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    token = request.app.state.demo_token
    if (
        not token
        or credentials is None
        or not secrets.compare_digest(
            credentials.credentials.encode("utf-8"), token.encode("utf-8")
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="演示数据接口需要有效的 Bearer 令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )


router = APIRouter(
    prefix="/api/demo", tags=["demo"], dependencies=[Depends(require_demo_access)]
)


@router.post("/seed")
def seed(memory: MemoryDependency, payload: NamespaceRequest | None = None):
    user_id = (payload or NamespaceRequest()).user_id
    return {"events": seed_demo(memory, user_id), "stats": memory.stats(user_id)}
