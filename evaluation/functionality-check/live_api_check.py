"""Exercise the running service with synthetic, separately scoped test data."""

import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).parent
USER = "qa-api-" + uuid4().hex[:12]
OTHER = USER + "-other"
BASE = "http://127.0.0.1:8765"
results = []


def request(method, path, data=None, status=200):
    payload = None if data is None else json.dumps(data, ensure_ascii=False).encode()
    req = Request(BASE + path, data=payload, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=20) as response:
            actual, body = response.status, response.read()
    except HTTPError as error:
        actual, body = error.code, error.read()
    parsed = json.loads(body)
    assert actual == status, f"HTTP {actual}, expected {status}"
    return parsed


def objects(module, user=USER):
    return request("GET", f"/api/architecture/objects/{module}?user_id={quote(user)}")["items"]


def observe(event, text, analysis, task="task", policy="persist"):
    return request("POST", "/api/architecture/observe", {
        "observation": {"user_id": USER, "thread_id": "qa", "task_id": task,
                        "source_event_id": event, "content": text, "retention_policy": policy},
        "analysis": analysis})


def assertion(text, value="蓝绿色", correction=False):
    return {"subject": USER, "predicate": "favorite_color", "value": value,
            "evidence_text": text, "correction": correction}


def check(name, action):
    started = time.monotonic()
    try:
        detail = action()
        results.append({"name": name, "passed": True, "detail": detail, "seconds": round(time.monotonic()-started, 3)})
    except Exception as error:
        results.append({"name": name, "passed": False, "error": type(error).__name__, "detail": str(error), "seconds": round(time.monotonic()-started, 3)})


def require(condition, message):
    assert condition, message


source_ids = []
text = "我最喜欢蓝绿色。"
analysis = {"semantic_candidates": [assertion(text)], "working_state_patch": {"constraints": ["本次用英文"]}}
check("健康接口", lambda: require(request("GET", "/api/health")["status"] == "ok", "health"))
check("模型配置状态", lambda: require(request("GET", "/api/chat/status")["configured"], "model not configured"))

first = observe("preference", text, analysis)
source_ids.append(first["source_id"])
check("语义候选实际写入", lambda: require(first["operations"][0]["status"] == "succeeded" and len(objects("semantic_assertions")) == 1, "write"))
check("工作约束更新", lambda: require(request("GET", f"/api/architecture/working/qa/task?user_id={USER}")["constraints"] == ["本次用英文"], "constraints"))
check("新任务不继承临时约束", lambda: require(not request("GET", f"/api/architecture/working/qa/new-task?user_id={USER}")["constraints"], "leaked constraints"))
check("语义检索", lambda: require(len(request("POST", "/api/architecture/retrieve", {"user_id": USER, "thread_id": "qa", "task_id": "task", "query": "蓝绿色", "modules": ["semantic"]})["items"]) == 1, "retrieve"))
check("其他用户检索隔离", lambda: require(not request("POST", "/api/architecture/retrieve", {"user_id": OTHER, "thread_id": "qa", "task_id": "task", "query": "蓝绿色", "modules": ["semantic"]})["items"], "user leakage"))

retry = observe("preference", text, analysis)
check("相同来源重试幂等", lambda: require(retry["operations"][0]["id"] == first["operations"][0]["id"] and len(objects("semantic_assertions")) == 1, "duplicate assertion"))
bad = observe("unsupported", "你好。", {"semantic_candidates": [assertion("我喜欢紫色。", "紫色")]})
source_ids.append(bad["source_id"])
check("无原文依据拒绝写入", lambda: require(bad["operations"][0]["status"] == "failed" and len(objects("semantic_assertions")) == 1, "unsupported evidence written"))

correction_text = "更正，我现在最喜欢深蓝色。"
corrected = observe("correction", correction_text, {"semantic_candidates": [assertion(correction_text, "深蓝色", True)]})
source_ids.append(corrected["source_id"])
check("偏好更正保留历史版本", lambda: require(sorted(r["status"] for r in objects("semantic_assertions")) == ["current", "history"] and any(r["value"] == "深蓝色" and r["status"] == "current" for r in objects("semantic_assertions")), "versioning"))

event_text = "我完成了测试拼图。"
event_analysis = {"episode_candidates": [{"observation": event_text, "outcome": "succeeded"}]}
event1 = observe("event-1", event_text, event_analysis, "event-task")
event2 = observe("event-2", event_text, event_analysis, "event-task")
source_ids.extend([event1["source_id"], event2["source_id"]])
check("同文不同事件独立保存", lambda: require(len(objects("episode_events")) == 2, "merged distinct events"))
observe("event-2", event_text, event_analysis, "event-task")
check("同一事件重试不重复", lambda: require(len(objects("episode_events")) == 2, "duplicate event"))

before = len(objects("semantic_assertions"))
temporary = observe("temporary", "我喜欢紫色。", {"semantic_candidates": [assertion("我喜欢紫色。", "紫色")]}, "temporary-task", "no_long_term")
source_ids.append(temporary["source_id"])
check("仅任务保存不写长期事实", lambda: require(len(objects("semantic_assertions")) == before and not temporary["operations"], "no_long_term failed"))
before_sources, before_states = len(objects("source_records")), len(objects("working_states"))
private = observe("no-persist", "不落盘的测试消息", {}, "private-task", "no_persist")
check("不持久化不产生来源与状态", lambda: require(private["status"] == "not_persisted" and len(objects("source_records")) == before_sources and len(objects("working_states")) == before_states, "no_persist failed"))

installed = request("POST", "/api/architecture/procedures/install-builtins", {"user_id": USER})
check("内置程序登记", lambda: require(len(installed["items"]) == 5, "builtin count"))
normalizer = next(p for p in installed["items"] if p["implementation_ref"] == "text.normalize")
run_body = {"user_id": USER, "arguments": {"text": "one   two\n three"}, "run_key": "normalize-once", "thread_id": "qa", "task_id": "procedure-task"}
run = request("POST", f"/api/architecture/runs/{normalizer['id']}", run_body)
check("程序真实执行与结果记录", lambda: require(run["status"] == "succeeded" and run["result"] == {"text": "one two three"}, "execution"))
same_run = request("POST", f"/api/architecture/runs/{normalizer['id']}", run_body)
check("程序重试幂等", lambda: require(same_run["id"] == run["id"] and len(objects("procedure_runs")) == 1, "duplicate run"))
failed_run = request("POST", f"/api/architecture/runs/{normalizer['id']}", {**run_body, "run_key": "bad-arguments", "arguments": {}})
check("程序参数失败如实记录", lambda: require(failed_run["status"] == "failed", "false success"))

proposal = request("POST", "/api/architecture/procedures", {"user_id": USER, "proposal": {"description": "测试流程文字", "kind": "reasoning", "source_refs": [first["source_id"]]}})
check("普通流程只形成草稿", lambda: require(proposal["status"] == "draft" and proposal["implementation_ref"] is None, "proposal activated"))
check("未实现程序不能启用", lambda: request("POST", f"/api/architecture/procedures/{proposal['id']}/activate", {"user_id": USER}, status=400))
request("POST", f"/api/architecture/procedures/{normalizer['id']}/disable", {"user_id": USER})
check("停用程序不能执行", lambda: request("POST", f"/api/architecture/runs/{normalizer['id']}", {**run_body, "run_key": "disabled"}, status=400))
request("POST", f"/api/architecture/procedures/{normalizer['id']}/activate", {"user_id": USER})
check("禁止跨来源删除", lambda: request("DELETE", f"/api/architecture/sources/{first['source_id']}?user_id={OTHER}", status=404))
check("非法工作状态字段被拒绝", lambda: request("PATCH", "/api/architecture/working/qa/task", {"user_id": USER, "patch": {"user_id": OTHER}}, status=400))
check("空消息返回校验错误", lambda: request("POST", "/api/chat", {"user_id": USER, "message": " "}, status=400))

legacy = request("POST", "/api/memories", {"user_id": USER, "content": "测试收藏代号青石", "memory_type": "semantic", "memory_key": "qa_marker", "memory_value": "青石", "importance": .9, "confidence": .9}, status=201)
legacy_items = request("GET", f"/api/memories?user_id={USER}")["items"]
check("兼容记忆手动保存", lambda: require(len(legacy_items) == 1, "legacy write"))
check("兼容记忆本地搜索", lambda: require(any("青石" in row["content"] for row in request("POST", "/api/search", {"user_id": USER, "query": "青石"})["results"]), "legacy retrieval"))
request("DELETE", f"/api/memories/{legacy_items[0]['id']}?user_id={USER}")
check("兼容记忆删除", lambda: require(not request("GET", f"/api/memories?user_id={USER}")["items"], "legacy delete"))

for row in objects("source_records"):
    request("DELETE", f"/api/architecture/sources/{row['id']}?user_id={USER}")
for state in objects("working_states"):
    request("DELETE", f"/api/architecture/working/{quote(state['thread_id'])}/{quote(state['task_id'])}?user_id={USER}")
check("测试来源及派生知识清理", lambda: require(not objects("source_records") and not objects("semantic_assertions") and not objects("episode_events"), "cleanup"))

summary = {"test_user": USER, "checks": len(results), "passed": sum(r["passed"] for r in results), "failed": [r for r in results if not r["passed"]], "results": results,
           "scope": "Running API with explicit structured analysis; model extraction tested separately through browser. Builtin registry metadata may remain in isolated test namespace."}
(ROOT / "live-api-results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k:summary[k] for k in ["test_user", "checks", "passed", "failed"]}, ensure_ascii=False))
