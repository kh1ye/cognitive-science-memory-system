"""Live HTTP checks against an isolated copy, using synthetic test users only."""

import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, build_opener, ProxyHandler
from uuid import uuid4

BASE = "http://127.0.0.1:8766"
USER = "qa-http-20261101-" + uuid4().hex[:8]
OTHER = USER + "-other"
RESULTS = []
OPENER = build_opener(ProxyHandler({}))


def request(method, path, data=None, status=200):
    payload = None if data is None else json.dumps(data, ensure_ascii=False).encode()
    req = Request(BASE + path, data=payload, method=method,
                  headers={"Content-Type": "application/json"})
    try:
        with OPENER.open(req, timeout=30) as response:
            actual, body = response.status, response.read()
    except HTTPError as error:
        actual, body = error.code, error.read()
    parsed = json.loads(body)
    assert actual == status, (actual, status, parsed)
    return parsed


def case(name):
    def run(action):
        start = time.monotonic()
        try:
            detail = action()
            result = {"name": name, "passed": True, "detail": detail}
        except Exception as error:
            result = {"name": name, "passed": False,
                      "error": type(error).__name__, "detail": str(error)}
        result["seconds"] = round(time.monotonic() - start, 3)
        RESULTS.append(result)
    return run


def objects(module, user=USER):
    return request("GET", f"/api/architecture/objects/{module}?user_id={quote(user)}")["items"]


def records(user=USER):
    return request("GET", f"/api/memories?user_id={user}&view=all&include_archived=true&limit=1000")["items"]


def add(content, **values):
    return request("POST", "/api/memories", {"user_id": USER, "content": content, **values}, 201)


def observe(event, text, analysis, **values):
    return request("POST", "/api/architecture/observe", {
        "observation": {"user_id": USER, "thread_id": "qa", "task_id": "task",
                        "source_event_id": event, "content": text, **values},
        "analysis": analysis})


def retrieve(query, user=USER, modules=None):
    return request("POST", "/api/architecture/retrieve", {
        "user_id": user, "thread_id": "qa", "task_id": "retrieval", "query": query,
        "modules": modules or ["semantic", "episodic"]})["items"]


@case("健康、配置及接口文档")
def _():
    assert request("GET", "/api/health")["status"] == "ok"
    paths = request("GET", "/openapi.json")["paths"]
    assert "/api/architecture/observe" in paths and "/api/evolution/analyze" in paths
    assert request("GET", "/api/config")["write_threshold"] == .42
    return request("GET", "/api/chat/status")


@case("手动写入与新架构共同存储、读取和来源")
def _():
    result = add("我喜欢用 Python 写脚本。", tags=["preference"],
                 memory_key="coding_language", memory_value="Python")
    assert result["decision"] == "WRITE_CURRENT"
    row = result["memory"]
    native = next(x for x in objects("semantic_assertions") if x["id"] == row["id"])
    assert native["_policy"]["write_score"] == row["write_score"]
    detail = request("GET", f"/api/memories/{row['id']}?user_id={USER}")
    assert detail["storage_kind"] == "typed"
    evidence = request("GET", f"/api/memories/{row['id']}/evidence?user_id={USER}")
    assert evidence["total_count"] == 1
    assert any(x["id"] == row["id"] for x in retrieve("我喜欢用什么语言写脚本"))
    return {"id": row["id"], "evidence_count": evidence["total_count"]}


@case("重复强化与同事件幂等")
def _():
    body = {"memory_key": "coding_language", "memory_value": "Python",
            "metadata": {"event_id": "python-confirm"}}
    first = add("我仍然喜欢用 Python 写脚本。", **body)
    second = add("我仍然喜欢用 Python 写脚本。", **body)
    assert first["decision"] == "REINFORCED" and second["decision"] == "UNCHANGED"
    assert first["memory"]["evidence_count"] == second["memory"]["evidence_count"] == 2


@case("冲突候选、双证据巩固与当前/历史检索")
def _():
    body = {"memory_key": "coding_language", "memory_value": "Rust", "tags": ["preference"]}
    candidate = add("现在改成喜欢用 Rust 写脚本。", **body)
    assert candidate["decision"] == "CANDIDATE"
    current = [r for r in records() if r["state_role"] == "current"]
    assert any(r["memory_value"] == "Python" for r in current)
    consolidated = add("再次确认，我目前喜欢用 Rust 写脚本。", **body)
    assert consolidated["decision"] == "CONSOLIDATED"
    for query, role, value in [("我现在用什么语言", "current", "Rust"),
                               ("以前Python", "history", "Python")]:
        result = request("POST", "/api/search", {"user_id": USER, "query": query})
        assert result["grounded"] and result["results"][0]["state_role"] == role
        assert result["results"][0]["memory_value"] == value
    return {"candidate": candidate["decision"], "update": consolidated["decision"]}


@case("低分留工作层、隐私拒写及原评分门槛")
def _():
    low = add("临时无价值碎片", tags=["noise"], importance=.1, confidence=.2)
    assert low["decision"] == "KEEP_SESSION_ONLY"
    assert any(x.get("id") == low["memory"]["id"] for x in objects("working_states"))
    assert all(x["id"] != low["memory"]["id"] for x in retrieve("临时无价值碎片"))
    for text, tags in [("不要记住测试信息", []), ("测试敏感内容", ["sensitive"])]:
        blocked = add(text, tags=tags)
        assert blocked["decision"] == "DROP" and blocked["memory"] is None


@case("类型化写入复用更新门控、更正不直接替换")
def _():
    def write(event, value, text, correction=False):
        return observe(event, text, {"semantic_candidates": [{"subject": USER,
            "predicate": "favorite_color", "value": value,
            "evidence_text": text, "correction": correction}]})
    write("color-1", "蓝绿色", "我喜欢蓝绿色。")
    write("color-2", "深蓝色", "更正，我现在喜欢深蓝色。", True)
    rows = objects("semantic_assertions")
    assert any(r["value"] == "蓝绿色" and r["status"] == "current" for r in rows)
    assert any(r["value"] == "深蓝色" and r["status"] == "candidate" for r in rows)
    write("color-3", "深蓝色", "再次确认，我喜欢深蓝色。", True)
    rows = objects("semantic_assertions")
    assert any(r["value"] == "深蓝色" and r["status"] == "current" for r in rows)
    assert any(r["value"] == "蓝绿色" and r["status"] == "history" for r in rows)


@case("来源幂等、无原文依据拒写和用户隔离")
def _():
    analysis = {"semantic_candidates": [{"subject": USER, "predicate": "test_marker",
        "value": "青石", "evidence_text": "测试代号是青石。"}]}
    first = observe("marker", "测试代号是青石。", analysis)
    again = observe("marker", "测试代号是青石。", analysis)
    assert first["operations"][0]["id"] == again["operations"][0]["id"]
    bad = observe("bad-source", "我的测试项目已经完成。", analysis)
    assert bad["operations"][0]["status"] == "failed"
    assert not retrieve("青石", OTHER)
    row = next(r for r in objects("semantic_assertions") if r.get("value") == "青石")
    request("GET", f"/api/memories/{row['id']}?user_id={OTHER}", status=404)
    request("DELETE", f"/api/architecture/sources/{first['source_id']}?user_id={OTHER}", status=404)


@case("任务约束隔离和不长期保存/不持久化策略")
def _():
    observe("constraint", "本次用英文。", {"working_state_patch": {"constraints": ["本次用英文"]}})
    assert request("GET", f"/api/architecture/working/qa/task?user_id={USER}")["constraints"] == ["本次用英文"]
    assert not request("GET", f"/api/architecture/working/qa/new?user_id={USER}")["constraints"]
    before = len(objects("semantic_assertions"))
    observe("temporary", "我喜欢紫色。", {"semantic_candidates": [{"subject": USER,
        "predicate": "color", "value": "紫色", "evidence_text": "我喜欢紫色。"}]}, retention_policy="no_long_term")
    assert len(objects("semantic_assertions")) == before
    counts = [len(objects(m)) for m in ["working_states", "source_records"]]
    receipt = observe("private", "不落盘的测试消息", {}, retention_policy="no_persist")
    assert receipt["status"] == "not_persisted"
    assert counts == [len(objects(m)) for m in ["working_states", "source_records"]]


@case("用户经历同文强化、事件重试和情景召回")
def _():
    a = {"episode_candidates": [{"observation": "我完成了测试拼图。", "outcome": "succeeded"}]}
    observe("episode-1", "我完成了测试拼图。", a)
    observe("episode-2", "我完成了测试拼图。", a)
    observe("episode-2", "我完成了测试拼图。", a)
    rows = [r for r in objects("episode_events") if r["observation"] == "我完成了测试拼图。"]
    assert len(rows) == 1 and rows[0]["_policy"]["evidence_count"] == 2
    assert any(r["id"] == rows[0]["id"] for r in retrieve("测试拼图"))


@case("结构化演化实际写入与新架构召回")
def _():
    trace = request("POST", "/api/evolution", {"user_id": USER,
        "content": "测试收藏代号是青铜。", "memory_key": "collection_marker", "memory_value": "青铜"}, 201)
    row = trace["result"]["memory"]
    assert any(r["id"] == row["id"] for r in objects("semantic_assertions"))
    assert any(r["id"] == row["id"] for r in retrieve("青铜"))


@case("程序登记、执行成功、幂等、参数失败及停用限制")
def _():
    installed = request("POST", "/api/architecture/procedures/install-builtins", {"user_id": USER})["items"]
    p = next(r for r in installed if r["implementation_ref"] == "text.normalize")
    body = {"user_id": USER, "arguments": {"text": "one   two\n three"}, "run_key": "normalize-once"}
    run = request("POST", f"/api/architecture/runs/{p['id']}", body)
    assert run["status"] == "succeeded" and run["result"] == {"text": "one two three"}
    assert request("POST", f"/api/architecture/runs/{p['id']}", body)["id"] == run["id"]
    failed = request("POST", f"/api/architecture/runs/{p['id']}", {**body, "run_key": "bad", "arguments": {}})
    assert failed["status"] == "failed"
    request("POST", f"/api/architecture/procedures/{p['id']}/disable", {"user_id": USER})
    request("POST", f"/api/architecture/runs/{p['id']}", {**body, "run_key": "disabled"}, 400)
    request("POST", f"/api/architecture/procedures/{p['id']}/activate", {"user_id": USER})
    return {"result": run["result"], "failed_status": failed["status"]}


@case("普通程序文本不会自动成为执行能力")
def _():
    source = next(s for s in objects("source_records") if s["content"] == "测试代号是青石。")
    p = request("POST", "/api/architecture/procedures", {"user_id": USER,
        "proposal": {"description": "测试时先检查再报告", "kind": "reasoning", "source_refs": [source["id"]]}})
    assert p["status"] == "draft" and p["implementation_ref"] is None
    request("POST", f"/api/architecture/procedures/{p['id']}/activate", {"user_id": USER}, 400)


@case("总览、主列表和分类计数一致")
def _():
    rows = records()
    overview = request("GET", f"/api/overview?user_id={USER}")
    assert len(rows) == overview["total_count"]
    assert sum(overview["by_type"].values()) == len(rows)
    assert len({r["id"] for r in rows}) == len(rows)
    return {"total": len(rows), "by_type": overview["by_type"]}


@case("保留度检查可调用且保护偏好保持当前")
def _():
    result = request("POST", "/api/maintenance/retention", {"user_id": USER})
    assert any(r["memory_value"] == "Rust" and r["state_role"] == "current" for r in records())
    return result


@case("会话创建、读取、隔离和删除")
def _():
    request("POST", "/api/sessions", {"user_id": USER, "thread_id": "qa-http-session"}, 201)
    request("GET", f"/api/sessions/qa-http-session?user_id={USER}")
    request("GET", f"/api/sessions/qa-http-session?user_id={OTHER}", status=404)
    request("DELETE", f"/api/sessions/qa-http-session?user_id={USER}")
    request("GET", f"/api/sessions/qa-http-session?user_id={USER}", status=404)


@case("删除记忆及来源派生记录")
def _():
    row = add("这是一条用于删除检查的测试内容。", memory_key="delete_check")["memory"]
    request("DELETE", f"/api/memories/{row['id']}?user_id={USER}")
    request("GET", f"/api/memories/{row['id']}?user_id={USER}", status=404)
    source = next(s for s in objects("source_records") if s["content"] == "测试代号是青石。")
    request("DELETE", f"/api/architecture/sources/{source['id']}?user_id={USER}")
    assert all(r.get("value") != "青石" for r in objects("semantic_assertions"))


@case("错误输入、未知接口和默认关闭的演示重置")
def _():
    request("POST", "/api/chat", {"user_id": USER, "message": " "}, 400)
    request("PATCH", "/api/architecture/working/qa/task", {"user_id": USER, "patch": {"user_id": OTHER}}, 400)
    request("GET", "/api/nonexistent", status=404)
    request("POST", "/api/demo/seed", {"user_id": USER}, 404)


@case("评测中心数据集、历史、结果和样本读取")
def _():
    datasets = request("GET", "/api/evaluations/datasets")["items"]
    assert len(datasets) == 3
    runs = request("GET", "/api/evaluations/runs")["items"]
    assert runs
    samples = []
    for run in runs:
        detail = request("GET", f"/api/evaluations/runs/{run['id']}")
        samples = detail.get("samples", [])
        if samples:
            sample_id = samples[0].get("sample_id") or samples[0].get("id")
            request("GET", f"/api/evaluations/runs/{run['id']}/samples/{sample_id}")
            break
    assert samples, "没有可读取的样本"
    request("GET", "/api/evaluations/tasks")
    return {"datasets": len(datasets), "runs": len(runs), "samples_in_checked_run": len(samples)}


summary = {"base_url": BASE, "test_user": USER, "checks": len(RESULTS),
           "passed": sum(r["passed"] for r in RESULTS), "results": RESULTS}
Path(__file__).with_name("live-results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(summary, ensure_ascii=False, indent=2))
