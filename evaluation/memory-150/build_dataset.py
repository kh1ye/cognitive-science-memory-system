import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
names = {
    "working": "工作记忆",
    "episodic": "情景记忆",
    "semantic": "语义记忆",
    "procedural": "程序记忆",
    "low_value": "低价值信息",
}
old = json.loads((BASE / "project-memory-challenge-100/cases.json").read_text())[
    "cases"
]
extra = json.loads((BASE / "memory-classifier-v2/holdout.json").read_text())["cases"]
rows = []
for kind in list(names)[:4]:
    selected = [r for r in old if r["memory_type"] == kind] + [
        r for r in extra if r["memory_type"] == kind
    ][:5]
    assert len(selected) == 30
    for r in selected:
        rows.append(
            {
                "id": f"T{len(rows) + 1:03d}",
                "category": kind,
                "expected": kind,
                "example": r["example"],
                "origin_id": r["id"],
                "evaluation": "concept_classification",
            }
        )
noise = [
    "在吗",
    "在不在",
    "有人吗？",
    "你好！",
    "您好",
    "嗨",
    "hello",
    "早上好",
    "好的",
    "收到",
    "知道了",
    "谢谢你",
    "嗯嗯",
    "哦哦",
    "OK",
    "哈哈哈",
    "。。。",
    "😊",
    "aaaaaa",
    "测试一下",
    "喂，能听见吗？",
    "辛苦啦",
    "好嘞",
    "我试一下能不能发出去",
    "路过打个招呼",
    "嗯嗯，明白了",
    "哈哈，笑死我了",
    "asdfghjkl",
    "这是一条测试消息",
    "1+1等于几？",
]
for text in noise:
    rows.append(
        {
            "id": f"T{len(rows) + 1:03d}",
            "category": "low_value",
            "expected": "context_only",
            "example": text,
            "evaluation": "live_chat_storage",
        }
    )
assert len(rows) == 150 and len({r["example"] for r in rows}) == 150
raw = (
    json.dumps(
        {
            "version": "memory-150-v1",
            "limitations": "作者参考标签；前120条为人类概念分类，后30条为存储策略测试；两种指标分开报告。",
            "cases": rows,
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n"
).encode()
(ROOT / "cases.json").write_bytes(raw)
(ROOT / "frozen-manifest.json").write_text(
    json.dumps(
        {
            "count": 150,
            "counts": {k: sum(r["category"] == k for r in rows) for k in names},
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        ensure_ascii=False,
        indent=2,
    )
)
lines = [
    "# 固定150条记忆测试集",
    "",
    "四类记忆各30条，低价值输入30条。前120条按人类记忆概念标注；低价值输入预期只保留上下文。作者自建标签，非独立标准基准。",
    "",
    "|编号|测试样例|预期|",
    "|---|---|---|",
]
for r in rows:
    lines.append(
        f"|{r['id']}|{r['example']}|{names[r['category']]}{'（仅上下文）' if r['category'] == 'low_value' else ''}|"
    )
(ROOT / "cases.md").write_text("\n".join(lines) + "\n")
