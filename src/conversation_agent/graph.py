"""A linear retrieve → reply → remember graph with SQLite checkpoints."""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from cognitive_memory import Memory
from cognitive_memory.retrieval.lexical import normalize_text

from .llm import ChatModelError, LLMSettings
from .memory import CognitiveMemory
from .prompts import DIALOGUE_PROMPT, EXTRACTION_PROMPT
from .state import ConversationState, MemoryExtraction


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
        builder.add_node("retrieve", self._retrieve)
        builder.add_node("reply", self._reply)
        builder.add_node("remember", self._remember)
        builder.add_edge(START, "retrieve")
        builder.add_edge("retrieve", "reply")
        builder.add_edge("reply", "remember")
        builder.add_edge("remember", END)
        self.graph = builder.compile(checkpointer=self.checkpointer)

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

    def _retrieve(self, state):
        message = state["messages"][-1]
        recent = " ".join(
            str(m.content)
            for m in state["messages"][:-1]
            if isinstance(m, HumanMessage)
        )[-2000:]
        return {
            "references": self.memory.retrieve(
                state["user_id"], str(message.content), recent
            ),
            "memory_results": [],
            "warnings": [],
        }

    def _reply(self, state):
        # Bound the model context without discarding the durable transcript.
        history = state["messages"][-20:]
        if history and isinstance(history[0], AIMessage):
            history = history[1:]
        messages = [
            SystemMessage(
                content=DIALOGUE_PROMPT
                + json.dumps(state["references"], ensure_ascii=False)
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

    def _remember(self, state):
        user_message = state["messages"][-2]
        results, warnings = [], []
        if state["auto_remember"] and self.memory.allows_extraction(
            str(user_message.content)
        ):
            try:
                extractor = self._get_model().with_structured_output(
                    MemoryExtraction, method="function_calling"
                )
                extraction = MemoryExtraction.model_validate(
                    extractor.invoke(
                        [
                            SystemMessage(content=EXTRACTION_PROMPT),
                            HumanMessage(content=str(user_message.content)),
                        ]
                    )
                )
                results = self.memory.write(
                    state["user_id"],
                    str(user_message.content),
                    extraction,
                    state["thread_id"],
                )
            except Exception:  # noqa: BLE001 -- preserve the answer across provider/storage failures
                # A successful conversation must survive extraction/provider/write failures.
                warnings.append(
                    "本轮回答已保存，但自动记忆处理未完成；可手动保存重要信息。"
                )
        reply = state["messages"][-1]
        return {
            "memory_results": results,
            "warnings": warnings,
            "messages": [
                AIMessage(
                    id=reply.id,
                    content=reply.content,
                    additional_kwargs={
                        "references": state["references"],
                        "memory_results": results,
                        "warnings": warnings,
                    },
                )
            ],
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

    def chat(self, user_id: str, thread_id: str, message: str, *, auto_remember=True):
        user_id = normalize_text(user_id) or "demo-user"
        with self._lock:
            self._get_model()  # Fail clearly before writing a checkpoint if unconfigured.
            self.create_session(user_id, thread_id, message[:20])
            config = self._config(user_id, thread_id)
            state = self.graph.invoke(
                {
                    "messages": [HumanMessage(content=message, id=str(uuid4()))],
                    "user_id": user_id,
                    "thread_id": thread_id,
                    "auto_remember": auto_remember,
                },
                config,
            )
            with self.checkpointer.cursor() as cursor:
                cursor.execute(
                    "UPDATE conversation_threads SET updated_at=?, "
                    "title=CASE WHEN title='新会话' THEN ? ELSE title END WHERE id=?",
                    (time.time(), message[:20], config["configurable"]["thread_id"]),
                )
            return {
                "thread_id": thread_id,
                "answer": state["messages"][-1].content,
                "references": state["references"],
                "memory_results": state["memory_results"],
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
                        "refs": data.get("references", []),
                        "memory_results": data.get("memory_results", []),
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
            with self.checkpointer.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM conversation_threads WHERE id=?", (internal_id,)
                )
            return True

    def close(self):
        with self._lock:
            self._conn.close()
