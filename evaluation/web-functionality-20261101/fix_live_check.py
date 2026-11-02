"""Verify the repaired configuration against the real model on the isolated server."""
import json
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).parent
USER = "qa-fix-20261101"
opener = build_opener(ProxyHandler({}))
results = {}


def call(method, path, data=None, status=200):
    payload = None if data is None else json.dumps(data, ensure_ascii=False).encode()
    req = Request("http://127.0.0.1:8766" + path, data=payload, method=method,
                  headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=240) as response:
        assert response.status == status
        return json.load(response)


try:
    results["model_status"] = call("GET", "/api/chat/status")
    assert results["model_status"]["model"] == "MiniMax-M3"
    learned = call("POST", "/api/chat", {"user_id": USER, "thread_id": "learn",
        "source_event_id": "fruit-message", "message": "我最喜欢的水果是杨桃。", "auto_remember": True})
    results["auto_memory"] = learned
    assert learned["answer"] and learned["memory_status"] == "processed", learned
    assert learned["memory_results"] and all(x["status"] == "succeeded" for x in learned["memory_results"]), learned
    memory_id = learned["memory_results"][0]["result_refs"][0]
    evidence = call("GET", f"/api/memories/{memory_id}/evidence?user_id={USER}")
    results["chat_evidence"] = evidence
    assert evidence["items"][0]["thread_id"] == "learn"
    assert evidence["items"][0]["message_id"] == "fruit-message"
    recalled = call("POST", "/api/chat", {"user_id": USER, "thread_id": "recall",
        "message": "我最喜欢的水果是什么？", "auto_remember": False})
    results["cross_session_recall"] = recalled
    assert "杨桃" in recalled["answer"] and any("杨桃" in r["content"] for r in recalled["references"]), recalled
    session = call("GET", f"/api/sessions/learn?user_id={USER}")
    results["source_session"] = session
    assert any(m["id"] == "fruit-message" and m["role"] == "user" for m in session["messages"])
    evolved = call("POST", "/api/evolution/analyze", {"user_id": USER, "content": "我喜欢用 Python 写脚本。"}, 201)
    results["model_evolution"] = evolved
    assert evolved["extraction"]["method"] == "model" and evolved["traces"], evolved
    assert any(t["result"]["memory"] for t in evolved["traces"]), evolved
    manual = call("POST", "/api/memories", {"user_id": USER, "content": "我的网页测试代号是青柠。"}, 201)
    results["manual_evidence"] = call("GET", f"/api/memories/{manual['memory']['id']}/evidence?user_id={USER}")
    assert all(not x["thread_id"] and not x["message_id"] for x in results["manual_evidence"]["items"])
    results["passed"] = True
except Exception as error:
    results["passed"] = False
    results["error"] = {"type": type(error).__name__, "message": str(error)[:2000]}
finally:
    (ROOT / "fix-live-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"user": USER, "passed": results["passed"], "completed": list(results),
                      "error": results.get("error")}, ensure_ascii=False))
