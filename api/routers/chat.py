"""Conversation and session APIs; existing memory/retrieval APIs stay independent."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from conversation_agent import ConversationAgent
from conversation_agent.llm import ChatModelError, ModelNotConfigured

from ..responses import error_response
from ..schemas import ChatRequest, SessionRequest

router = APIRouter(prefix="/api", tags=["conversation"])


def get_agent(request: Request) -> ConversationAgent:
    return request.app.state.conversation_agent


AgentDependency = Annotated[ConversationAgent, Depends(get_agent)]


@router.get("/chat/status")
def status(agent: AgentDependency):
    return {"configured": agent.configured, "model": agent.settings.model}


@router.post("/chat")
def chat(payload: ChatRequest, agent: AgentDependency):
    try:
        return agent.chat(
            payload.user_id,
            payload.thread_id,
            payload.message,
            auto_remember=payload.auto_remember,
        )
    except ModelNotConfigured as error:
        return error_response(str(error), 503, "model_not_configured")
    except ChatModelError as error:
        return error_response(str(error), 502, "model_error")


@router.post("/sessions", status_code=201)
def create_session(payload: SessionRequest, agent: AgentDependency):
    return agent.create_session(payload.user_id, payload.thread_id)


@router.get("/sessions")
def sessions(agent: AgentDependency, user_id: str = "demo-user"):
    return {"items": agent.list_sessions(user_id)}


@router.get("/sessions/{thread_id}")
def session(thread_id: str, agent: AgentDependency, user_id: str = "demo-user"):
    result = agent.get_session(user_id, thread_id)
    return (
        result if result is not None else error_response("会话不存在", 404, "not_found")
    )


@router.delete("/sessions/{thread_id}")
def delete_session(thread_id: str, agent: AgentDependency, user_id: str = "demo-user"):
    if agent.delete_session(user_id, thread_id):
        return {"deleted": True, "thread_id": thread_id}
    return error_response("会话不存在", 404, "not_found")
