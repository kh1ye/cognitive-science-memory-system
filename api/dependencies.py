"""Dependencies shared by the API routers."""

from typing import Annotated

from fastapi import Depends, Request

from cognitive_memory import Memory


def get_memory(request: Request) -> Memory:
    return request.app.state.memory


MemoryDependency = Annotated[Memory, Depends(get_memory)]
