"""Real-model API smoke test. All conversations live in disposable in-memory stores."""
import json
from pathlib import Path
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient
from api.app import create_app
from cognitive_memory import Memory
from conversation_agent.llm import LLMSettings
from cognitive_memory.profile import UserProfile

ROOT = Path(__file__).resolve().parent
# Expectations are manual test targets, not externally annotated ground truth.
CASES = [
    ("元气", "一觉醒来精力特别充沛，现在干劲十足，想把积压的事都推进！", ["energetic"]),
    ("开心", "刚收到录取通知，我现在特别开心，忍不住想笑！", ["happy"]),
    ("平静", "忙完坐在窗边听雨，心里很安稳，整个人松弛下来了。", ["calm"]),
    ("中性任务", "请帮我列一下明天会议的议程。", ["neutral"]),
    ("疲惫", "今天连续开了六个小时的会，我现在困得睁不开眼，只想睡觉。", ["tired"]),
    ("难过", "刚和很重要的朋友告别，我心里空落落的，特别难过。", ["sad"]),
    ("焦虑", "十分钟后就要面试了，我一直担心答不上来，心跳得很快。", ["anxious"]),
    ("烦躁", "同一个问题反复出错，我现在烦得不行，什么都不想听了。", ["irritable"]),
    ("含蓄开心", "终于等到这一刻了！项目验收全过，我嘴角就没下来过。", ["happy", "energetic"]),
    ("含蓄疲惫", "我盯着屏幕半天，一个字都看不进去，脑子像没电了一样。", ["tired"]),
    ("反讽", "真是太棒了，忙了一整天的文件全丢了，我都快气炸了。", ["irritable"]),
    ("否定", "我现在不焦虑，也不难过，状态挺平常的。先说正事吧。", ["neutral", "calm"]),
    ("他人引用", "我同事说：‘我快焦虑死了。’你帮我想想怎么安慰他。", ["neutral"]),
    ("翻译", "翻译成英文：‘我好难过，今晚什么也不想做。’", ["neutral"]),
    ("假设", "假如我明天特别紧张，应该怎么调整呼吸？", ["neutral"]),
    ("角色台词", "写一段角色台词：我好生气，我现在要发火了！", ["neutral"]),
    ("代码字段", "'emotion': 'sad' 字段一般如何命名？我是在写代码。", ["neutral"]),
    ("历史感受", "去年考试前我特别焦虑，不过现在说的只是当时的经历。", ["neutral"]),
    ("概念讨论", "开心、悲伤和焦虑在心理学上怎么区分？", ["neutral"]),
    ("不明确", "嗯，知道了。", ["neutral"]),
    ("多轮-低落", "今天遇到一些事，我现在心里很难受。", ["sad"]),
    ("多轮-保持", "先不聊这个，你给我讲个小故事吧。", ["sad"]),
    ("多轮-恢复", "跟朋友聊完我现在已经放松多了，心里很平静，不难受了。", ["calm", "neutral"]),
    ("多轮-疲惫", "聊到这里，我已经困得不行了，先睡啦。", ["tired"]),
    ("新会话隔离", "请帮我写一个Python排序例子。", ["neutral"]),
    ("no_persist", "我现在被这些事弄得很烦躁，先别记录任何内容。", ["irritable"]),
]


def main():
    settings = LLMSettings.from_env()
    model = settings.create_model()
    results = []
    started = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    output = ROOT / "results.json"
    with Memory(":memory:") as memory:
        with TestClient(create_app(service=memory, chat_db_path=":memory:", chat_model=model)) as client:
            agent = client.app.state.conversation_agent
            for index, (name, message, expected) in enumerate(CASES, 1):
                thread = "multi-turn" if 21 <= index <= 24 else f"case-{index:02d}"
                no_persist = name == "no_persist"
                before = [agent._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("checkpoints", "writes", "conversation_threads")]
                start = time.monotonic()
                item = {"index": index, "name": name, "message": message, "thread_id": thread,
                        "expected_labels": expected, "retention_policy": "no_persist" if no_persist else "persist", "auto_remember": False}
                try:
                    response = client.post("/api/chat", json={"user_id": "emotion-evaluation", "thread_id": thread,
                        "message": message, "auto_remember": False, "retention_policy": item["retention_policy"]})
                    data = response.json()
                    emotion = data.get("emotion", {})
                    after = [agent._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("checkpoints", "writes", "conversation_threads")]
                    item.update(http_status=response.status_code, emotion=emotion, answer=data.get("answer", ""),
                        warnings=data.get("warnings", []), memory_status=data.get("memory_status"),
                        label_matches=response.status_code == 200 and emotion.get("label") in expected,
                        no_persist_writes_unchanged=(before == after) if no_persist else None)
                except Exception as error:
                    item.update(error=type(error).__name__, label_matches=False)
                item["elapsed_seconds"] = round(time.monotonic()-start, 3)
                results.append(item)
                payload = {"model": settings.model, "provider": settings.provider, "started_at": started,
                    "method": "real configured model, full /api/chat pipeline, disposable in-memory databases, auto_remember=false, manual expected labels",
                    "completed": len(results), "planned": len(CASES), "results": results}
                output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
                print(json.dumps({"index": index, "name": name, "expected": expected,
                    "actual": item.get("emotion"), "match": item["label_matches"], "seconds": item["elapsed_seconds"]}, ensure_ascii=False), flush=True)
            payload["checks"] = {
                "profile_empty": UserProfile.read(memory, "emotion-evaluation").items == [],
                "semantic_empty": memory.architecture.repo.rows("semantic_assertions", "emotion-evaluation") == [],
                "episodes_empty": memory.architecture.repo.rows("episode_events", "emotion-evaluation") == [],
                "procedures_empty": not any(row.get("implementation_ref") for row in memory.architecture.repo.rows("procedure_versions", "emotion-evaluation")),
                "emotion_pending_writes": agent._conn.execute("SELECT COUNT(*) FROM writes WHERE channel='emotion'").fetchone()[0],
            }
            payload["finished_at"] = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
            payload["matches"] = sum(item["label_matches"] for item in results)
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print("COMPLETE", payload["matches"], "/", len(CASES), json.dumps(payload["checks"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
