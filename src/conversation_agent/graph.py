"""Bounded observe/decide/execute loop using LangGraph checkpoints."""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from cognitive_memory import Memory
from cognitive_memory.architecture_models import (
    Action,
    Observation,
    ObservationAnalysis,
)
from cognitive_memory.models import iso_now
from cognitive_memory.retrieval.lexical import normalize_text

from .llm import ChatModelError, LLMSettings, analyze_observation
from .memory import CognitiveMemory
from .prompts import DIALOGUE_PROMPT
from .state import ConversationState


class ConversationAgent:
    """One local service owns its checkpointer; Memory remains caller-owned.

    Operations are serialized for the project's single-process SQLite deployment.
    Each thread gets history from its own checkpoints; long-term memory is user-scoped.
    """

    def __init__(
        self, engine: Memory, db_path: str | Path, *, model=None, settings=None
    ):
        self.memory = CognitiveMemory(engine)
        self.settings = settings or LLMSettings.from_env()
        self._model = model
        self._lock = threading.RLock()
        path = str(db_path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self._conn)
        self.checkpointer.setup()
        with self.checkpointer.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_threads (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(user_id, thread_id)
                )
            """)
        builder = StateGraph(ConversationState)
        builder.add_node("observe", self._observe)
        builder.add_node("decide", self._decide)
        builder.add_node("execute", self._execute)
        builder.add_edge(START, "observe")
        builder.add_edge("observe", "decide")
        builder.add_conditional_edges(
            "decide",
            lambda state: "end" if state["stop_reason"] else "execute",
            {"end": END, "execute": "execute"},
        )
        builder.add_edge("execute", "decide")
        self.graph = builder.compile(checkpointer=self.checkpointer)
        self.ephemeral_graph = builder.compile()
        self.memory.engine.architecture.source_delete_hooks.append(
            self._purge_source_session
        )

    def _purge_source_session(self, user, thread):
        # Older checkpoint revisions may contain retrieved/derived prose. Conservatively
        # remove this user's conversation checkpoints rather than inspect only latest state.
        for session in self.list_sessions(user):
            self.delete_session(user, session["id"])

    def _observe(self, state):
        architecture = self.memory.engine.architecture
        message = str(state["messages"][-1].content)
        analysis, warnings = ObservationAnalysis(), []
        if (
            state["auto_remember"]
            and state["retention_policy"] != "no_persist"
            and self.memory.allows_extraction(message)
        ):
            try:
                analysis = analyze_observation(
                    self._get_model(),
                    "user_id=" + state["user_id"] + "\n" + message,
                    source_content=message,
                )
            except Exception:  # noqa: BLE001 -- preserve reply and report extraction/learning failure
                warnings.append("结构化提取失败；本轮未确认保存长期记忆。")
        working = architecture.working_state(
            state["user_id"], state["thread_id"], state["task_id"]
        )
        observation = Observation(
            user_id=state["user_id"],
            thread_id=state["thread_id"],
            task_id=state["task_id"],
            source_event_id=state["observation_id"],
            content=message,
            observed_at=iso_now(),
            retention_policy="no_long_term"
            if any(s.sensitive for s in analysis.semantic_candidates)
            else state["retention_policy"],
        )
        # Runtime updates first; learning is a separately selected action below.
        if state["retention_policy"] != "no_persist":
            architecture.observe(
                observation,
                analysis.model_copy(
                    update={
                        "episode_candidates": [],
                        "semantic_candidates": [],
                        "procedure_proposals": [],
                    }
                ),
            )
        return {
            "analysis": analysis.model_dump(),
            "completed_actions": [],
            "steps": 0,
            "stop_reason": "",
            "references": [],
            "memory_results": [],
            "warnings": warnings,
            "memory_status": "disabled",
            "working": working.model_dump(),
        }

    def _decide(self, state):
        completed = state["completed_actions"]
        candidates = [
            Action(name=name, reason=reason)
            for name, reason in [
                ("retrieve", "Fill knowledge gap from long-term memory"),
                ("reply", "Answer using available context"),
                ("learn", "Persist validated learning candidates"),
            ]
            if name not in completed
        ]
        stop = ""
        if state["steps"] >= 4:
            stop = "max_steps"
        elif not candidates:
            stop = "turn_complete"
        selected = candidates[0] if candidates else Action(name="stop", reason=stop)
        if selected.name in completed:
            stop = "repeated_action"
        patch = {
            "candidate_actions": [a.model_dump() for a in candidates],
            "selected_action": selected.model_dump(),
            "task_state": {"steps": state["steps"], "stop_reason": stop},
            "status": "paused" if stop else "active",
        }
        if state["retention_policy"] != "no_persist":
            self.memory.engine.architecture.update_working_state(
                state["user_id"], state["thread_id"], state["task_id"], patch
            )
        return {"selected_action": selected.model_dump(), "stop_reason": stop}

    def _execute(self, state):
        action = Action.model_validate(state["selected_action"])
        if action.name == "retrieve":
            query = str(state["messages"][-1].content)
            # Bounded fixed policy: explicit experience/capability requests route separately.
            modules = (
                ("episodic",)
                if any(w in query for w in ("以前", "上次", "经历"))
                else ("semantic",)
            )
            if any(w in query for w in ("程序", "工具", "能力")):
                modules = ("procedural",)
            if state["retention_policy"] == "no_persist":
                references = []
            else:
                references = self.memory.engine.catalog.retrieve(
                    state["user_id"],
                    state["thread_id"],
                    state["task_id"],
                    query,
                    modules=modules,
                )
            update = {"references": references}
        elif action.name == "reply":
            update = self._reply(state)
        elif action.name == "learn":
            update = self._learn(state)
        else:
            update = {}
        action.status = (
            "failed" if update.get("memory_status") == "failed" else "succeeded"
        )
        if state["retention_policy"] != "no_persist":
            self.memory.engine.architecture.update_working_state(
                state["user_id"],
                state["thread_id"],
                state["task_id"],
                {"selected_action": action.model_dump()},
            )
        return {
            **update,
            "completed_actions": [*state["completed_actions"], action.name],
            "steps": state["steps"] + 1,
        }

    def _learn(self, state):
        status, results, warnings = "disabled", [], list(state["warnings"])
        if state["auto_remember"] and state["retention_policy"] == "persist":
            try:
                content = str(
                    next(
                        m
                        for m in reversed(state["messages"])
                        if isinstance(m, HumanMessage)
                    ).content
                )
                if not self.memory.allows_extraction(content):
                    status = "privacy_blocked"
                elif warnings:
                    status = "failed"
                else:
                    result = self.memory.engine.architecture.observe(
                        Observation(
                            user_id=state["user_id"],
                            thread_id=state["thread_id"],
                            task_id=state["task_id"],
                            source_event_id=state["observation_id"],
                            content=content,
                        ),
                        state["analysis"],
                    )
                    results = result["operations"]
                    status = (
                        "failed"
                        if result["status"] == "partial_failure"
                        else (
                            "privacy_blocked"
                            if result["status"] == "no_long_term"
                            else ("processed" if results else "no_new_memory")
                        )
                    )
            except Exception:  # noqa: BLE001 -- preserve reply and report extraction/learning failure
                status = "failed"
            if status == "failed":
                warnings.append("回答已生成，但本轮长期记忆未全部保存成功。")
        reply = state["messages"][-1]
        return {
            "memory_results": results,
            "memory_status": status,
            "warnings": warnings,
            "messages": [
                AIMessage(
                    id=reply.id,
                    content=reply.content,
                    additional_kwargs={
                        "references": state["references"],
                        "memory_results": results,
                        "memory_status": status,
                        "warnings": warnings,
                    },
                )
            ],
        }

    @property
    def configured(self):
        return self._model is not None or bool(self.settings.api_key)

    def _get_model(self):
        if self._model is None:
            self._model = self.settings.create_model()
        return self._model

    @staticmethod
    def _config(user_id, thread_id):
        # Public IDs cannot select another user's checkpoint namespace.
        internal_id = str(uuid5(NAMESPACE_URL, json.dumps([user_id, thread_id])))
        return {"configurable": {"thread_id": internal_id}}

    def _reply(self, state):
        # Bound the model context without discarding the durable transcript.
        history = state["messages"][-20:]
        if history and isinstance(history[0], AIMessage):
            history = history[1:]
        messages = [
            SystemMessage(
                content=DIALOGUE_PROMPT
                + json.dumps(
                    {
                        "retrieved": state["references"],
                        "working": self.memory.engine.architecture.working_state(
                            state["user_id"], state["thread_id"], state["task_id"]
                        ).model_dump(),
                    },
                    ensure_ascii=False,
                )
            ),
            *history,
        ]
        try:
            response = self._get_model().invoke(messages)
            answer = response.text
            if not answer.strip():
                raise ValueError("Empty or non-text response")
        except Exception as error:
            logging.getLogger(__name__).warning(
                "Chat provider failed: %s (status=%s)",
                type(error).__name__,
                getattr(error, "status_code", None),
            )
            raise ChatModelError("模型调用失败，请检查模型配置或稍后重试。") from error
        return {
            "messages": [
                AIMessage(
                    content=answer,
                    id=f"reply:{state['messages'][-1].id}",
                    additional_kwargs={"references": state["references"]},
                )
            ]
        }

    def create_session(
        self, user_id: str, thread_id: str | None = None, title="新会话"
    ):
        user_id = normalize_text(user_id) or "demo-user"
        thread_id = thread_id or str(uuid4())
        internal_id = self._config(user_id, thread_id)["configurable"]["thread_id"]
        with self._lock, self.checkpointer.cursor() as cursor:
            cursor.execute(
                "INSERT OR IGNORE INTO conversation_threads VALUES (?, ?, ?, ?, ?)",
                (internal_id, user_id, thread_id, title, time.time()),
            )
        return self.get_session(user_id, thread_id)

    def chat(
        self,
        user_id: str,
        thread_id: str,
        message: str,
        *,
        auto_remember=True,
        task_id=None,
        source_event_id=None,
        retention_policy="persist",
    ):
        user_id = normalize_text(user_id) or "demo-user"
        with self._lock:
            self._get_model()  # Fail clearly before writing a checkpoint if unconfigured.
            if retention_policy not in ("persist", "no_long_term", "no_persist"):
                raise ValueError("Invalid retention policy")
            if retention_policy != "no_persist":
                self.create_session(user_id, thread_id, message[:20])
            config = self._config(user_id, thread_id)
            graph = (
                self.ephemeral_graph if retention_policy == "no_persist" else self.graph
            )
            observation_id = source_event_id or str(uuid4())
            new_messages = [HumanMessage(content=message, id=observation_id)]
            prior = (
                self.graph.get_state(config).values
                if retention_policy != "no_persist"
                else {}
            )
            if prior.get("task_id") and prior["task_id"] != (task_id or thread_id):
                new_messages = [RemoveMessage(id=REMOVE_ALL_MESSAGES), *new_messages]
            if retention_policy != "no_persist":
                self.memory.engine.architecture.register_model_configuration(
                    user_id, provider=self.settings.provider, model=self.settings.model
                )
            state = graph.invoke(
                {
                    "messages": new_messages,
                    "user_id": user_id,
                    "thread_id": thread_id,
                    "auto_remember": auto_remember,
                    "task_id": task_id or thread_id,
                    "observation_id": observation_id,
                    "retention_policy": "no_long_term"
                    if retention_policy == "persist" and not auto_remember
                    else retention_policy,
                },
                {**config, "recursion_limit": 16},
            )
            if retention_policy != "no_persist":
                with self.checkpointer.cursor() as cursor:
                    cursor.execute(
                        "UPDATE conversation_threads SET updated_at=?, "
                        "title=CASE WHEN title='新会话' THEN ? ELSE title END WHERE id=?",
                        (
                            time.time(),
                            message[:20],
                            config["configurable"]["thread_id"],
                        ),
                    )
            return {
                "thread_id": thread_id,
                "task_id": state["task_id"],
                "stop_reason": state["stop_reason"],
                "answer": state["messages"][-1].content,
                "references": state["references"],
                "memory_results": state["memory_results"],
                "memory_status": state["memory_status"],
                "warnings": state["warnings"],
            }

    def _session(self, row):
        internal_id, _user_id, thread_id, title, updated_at = row
        snapshot = self.graph.get_state({"configurable": {"thread_id": internal_id}})
        messages = []
        for message in snapshot.values.get("messages", []):
            if isinstance(message, (HumanMessage, AIMessage)):
                data = message.additional_kwargs
                messages.append(
                    {
                        "role": "user"
                        if isinstance(message, HumanMessage)
                        else "assistant",
                        "text": message.content,
                        "id": message.id,
                        "refs": data.get("references", []),
                        "memory_results": data.get("memory_results", []),
                        "memory_status": data.get("memory_status", ""),
                        "warnings": data.get("warnings", []),
                    }
                )
        return {
            "id": thread_id,
            "title": title,
            "messages": messages,
            "updated_at": updated_at,
            "persisted": True,
        }

    def list_sessions(self, user_id: str):
        user_id = normalize_text(user_id) or "demo-user"
        with self._lock:
            with self.checkpointer.cursor(transaction=False) as cursor:
                rows = cursor.execute(
                    "SELECT * FROM conversation_threads WHERE user_id=? ORDER BY updated_at DESC LIMIT 100",
                    (user_id,),
                ).fetchall()
            return [self._session(row) for row in rows]

    def get_session(self, user_id: str, thread_id: str):
        user_id = normalize_text(user_id) or "demo-user"
        with self._lock:
            with self.checkpointer.cursor(transaction=False) as cursor:
                row = cursor.execute(
                    "SELECT * FROM conversation_threads WHERE user_id=? AND thread_id=?",
                    (user_id, thread_id),
                ).fetchone()
            return self._session(row) if row else None

    def delete_session(self, user_id: str, thread_id: str):
        user_id = normalize_text(user_id) or "demo-user"
        with self._lock:
            if self.get_session(user_id, thread_id) is None:
                return False
            internal_id = self._config(user_id, thread_id)["configurable"]["thread_id"]
            self.checkpointer.delete_thread(internal_id)
            architecture = self.memory.engine.architecture
            with architecture.storage.transaction():
                for runtime in architecture.repo.rows("working_states", user_id):
                    if runtime["thread_id"] == thread_id:
                        architecture.clear_task(user_id, thread_id, runtime["task_id"])
            with self.checkpointer.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM conversation_threads WHERE id=?", (internal_id,)
                )
            return True

    def close(self):
        with self._lock:
            hooks = self.memory.engine.architecture.source_delete_hooks
            if self._purge_source_session in hooks:
                hooks.remove(self._purge_source_session)
            self._conn.close()
