"""Import versioned, clearly labelled emotion examples into local chat history.

No model calls, no long-term memory writes, no automatic startup seeding.
"""
import argparse
import json
import os
from pathlib import Path
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, RemoveMessage

from cognitive_memory import Memory
from cognitive_memory.retrieval.lexical import normalize_text
from conversation_agent import ConversationAgent
from conversation_agent.llm import LLMSettings

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/assistant-emotions/conversations.json"
DEFAULT_SESSIONS = ROOT / "memory_product/data/memory_demo_sessions.db"
NOTICE = "这是一组情绪识别示例：输入为人工编写的测试情境，回答来自真实模型。不是当前用户的个人经历，不应据此建立用户画像或推断用户当前情绪。"


def seed_conversations(agent, fixture, user_id="demo-user"):
    user = normalize_text(user_id)
    if not user or fixture.get("version") != 1:
        raise ValueError("Invalid user or fixture version")
    samples = fixture["conversations"]
    ids = set()
    # Validate the whole fixture before writing anything.
    for sample in samples:
        sid = sample["id"]
        if not re.fullmatch(r"emotion-example-[A-Za-z0-9_-]{1,80}", sid) or sid in ids:
            raise ValueError("Invalid or duplicate example identity")
        ids.add(sid)
        if not sample["title"].strip() or not sample["messages"] or len(sample["messages"]) % 2:
            raise ValueError("Examples must have a title and complete turns")
        for index, message in enumerate(sample["messages"]):
            if message["role"] != ("user" if index % 2 == 0 else "assistant") or not isinstance(message["text"], str) or not message["text"].strip():
                raise ValueError("Invalid example message")
    added, skipped, updated = [], [], []
    for sample in samples:
        sid = sample["id"]
        existing = agent.get_session(user, sid)
        messages = [SystemMessage(content=NOTICE, id=sid + "-notice")]
        for index, message in enumerate(sample["messages"]):
            cls = HumanMessage if message["role"] == "user" else AIMessage
            metadata = {"memory_status": "disabled", "example_emotion": sample["expected_emotions"][index // 2]} if message["role"] == "assistant" else {}
            messages.append(cls(content=message["text"], id=f"{sid}-{index}", additional_kwargs=metadata))
        if existing is not None:
            # Migrate only untouched fixture messages and the obsolete banner.
            # User continuations and edits must remain intact.
            old = {message["id"]: message for message in existing["messages"]}
            patches = []
            if sid + "-intro" in old:
                patches.append(RemoveMessage(id=sid + "-intro"))
            snapshot = agent.graph.get_state(agent._config(user, sid)).values
            stored = {message.id: message for message in snapshot.get("messages", [])}
            for message in messages:
                previous = stored.get(message.id)
                if (isinstance(message, AIMessage) and previous is not None
                    and previous.content == message.content and previous.additional_kwargs != message.additional_kwargs):
                    patches.append(message)
            renamed = existing["title"].startswith("[示例]") and existing["title"].removeprefix("[示例]").strip() == sample["title"]
            if renamed:
                with agent.checkpointer.cursor() as cursor:
                    cursor.execute("UPDATE conversation_threads SET title=? WHERE user_id=? AND thread_id=? AND title=?",
                                   (sample["title"], user, sid, existing["title"]))
            if patches:
                agent.graph.update_state(agent._config(user, sid), {"messages": patches}, as_node="decide")
            if patches or renamed:
                updated.append(sid)
            else:
                skipped.append(sid)
            continue
        # Import transcripts through the existing checkpointer, without invoking
        # observe/learn or reconstructing a live (short-lived) emotion state.
        agent.graph.update_state(agent._config(user, sid), {
            "messages": messages, "user_id": user, "thread_id": sid,
            "task_id": sid, "stop_reason": "turn_complete",
        }, as_node="decide")
        agent.create_session(user, sid, sample["title"])
        added.append(sid)
    return {"user_id": user, "added": added, "updated": updated, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="demo-user", help="Target local workspace")
    parser.add_argument("--sessions-db", default=os.getenv("CONVERSATION_DB_PATH") or str(DEFAULT_SESSIONS))
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text())
    # The real memory database is deliberately never opened by this importer.
    with Memory(":memory:") as memory:
        agent = ConversationAgent(memory, args.sessions_db, settings=LLMSettings())
        try:
            print(json.dumps(seed_conversations(agent, fixture, args.user), ensure_ascii=False, indent=2))
        finally:
            agent.close()


if __name__ == "__main__":
    main()
