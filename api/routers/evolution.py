from dataclasses import asdict
import re

from fastapi import APIRouter

from cognitive_memory import Memory
from cognitive_memory.keys import canonicalize_memory_key, canonicalize_memory_value
from cognitive_memory.retrieval.lexical import normalize_text
from conversation_agent.llm import ModelNotConfigured, extract_memories
from conversation_agent.memory import source_span
from conversation_agent.state import MemoryCandidate, MemoryExtraction
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..dependencies import MemoryDependency
from ..schemas import MemoryRequest
from ..responses import error_response
from .chat import AgentDependency

router = APIRouter(prefix="/api/evolution", tags=["evolution"])


class EvolutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="demo-user", min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=10000)

    @field_validator("content", "user_id")
    @classmethod
    def nonempty(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("输入不能为空")
        return value


def local_extraction(content):
    patterns = [
        (r"我(?:现在|目前|平时)?(?:更|最)?喜欢喝(咖啡|茶|牛奶|水)", "preferred_beverage"),
        (r"我(?:现在|目前|平时)?(?:更|最)?喜欢(?:使用|用)\s*(Python|Rust|JavaScript|Java|Go)", "preferred_programming_language"),
    ]
    for pattern, key in patterns:
        match = re.fullmatch(pattern + r"[。！.!]?", content, flags=re.IGNORECASE)
        if match:
            return MemoryExtraction(memories=[MemoryCandidate(
                content=content, memory_key=key, memory_value=match.group(1),
                tags=["preference"],
            )])
    return MemoryExtraction()


@router.post("/analyze", status_code=201)
def analyze(payload: EvolutionInput, memory: MemoryDependency, agent: AgentDependency):
    user_id = normalize_text(payload.user_id) or "demo-user"
    response = {
        "input": {"content": payload.content, "user_id": user_id},
        "extraction": {"method": "privacy_gate", "candidates": [], "rejected_count": 0},
        "traces": [],
        "outcome": "processed",
        "message": "所有步骤均为本次真实执行结果；不会自动补充确认消息或模拟后续证据。",
    }
    if memory.encoder.privacy_reason(normalize_text(payload.content), [], False):
        response["traces"] = [evolve(MemoryRequest(
            user_id=user_id, content=payload.content, source="evolution_workbench",
        ), memory)]
        response["outcome"] = "privacy_blocked"
        response["extraction"]["message"] = "识别到不记忆指令，在模型提取前停止处理。"
        return response
    if agent.configured:
        try:
            with agent._lock:
                extraction = extract_memories(agent._get_model(), payload.content)
        except ModelNotConfigured:
            return error_response("模型配置不可用，请检查配置并重启后端。本次未写入记忆。", 503, "model_not_configured")
        except Exception:
            return error_response("自动提取失败，本次未写入记忆。请检查模型连接后重试。", 502, "extraction_failed")
        response["extraction"].update({
            "method": "model",
            "message": "使用已配置的模型提取结构化信息，每条候选均需通过原文证据校验。",
        })
    else:
        extraction = local_extraction(payload.content)
        response["extraction"].update({
            "method": "local_rules",
            "message": "未配置模型，使用有限的本地规则：仅支持简单的饮品或编程语言偏好陈述。重要性 0.7、置信度 0.8 为规则默认参数，不是模型评估值。更复杂的输入需配置模型。",
        })
    candidates = []
    seen = set()
    for candidate in extraction.memories:
        evidence = source_span(candidate.content, payload.content)
        if evidence is None or evidence in seen:
            response["extraction"]["rejected_count"] += 1
            continue
        seen.add(evidence)
        memory_key = canonicalize_memory_key(candidate.memory_key)
        candidates.append(
            candidate.model_copy(
                update={
                    "content": evidence,
                    "memory_key": memory_key or "",
                    "memory_value": canonicalize_memory_value(
                        memory_key, candidate.memory_value, evidence
                    )
                    or "",
                }
            )
        )
    response["extraction"]["candidates"] = [item.model_dump() for item in candidates]
    if not candidates:
        response["outcome"] = "no_new_memory"
        response["message"] = (
            "本地规则未识别出支持的偏好陈述；更复杂的输入需配置模型。"
            if response["extraction"]["method"] == "local_rules"
            else "本次没有提取到通过原文证据校验的可用候选。"
        ) + "后续编码、比较、巩固和存储均未执行，没有写入记忆。"
        return response
    for candidate in candidates:
        tags = list(candidate.tags)
        if candidate.sensitive:
            tags.append("sensitive")
        values = candidate.model_dump(exclude={"sensitive"})
        values.update({"tags": tags, "user_id": user_id, "source": "evolution_workbench", "consent": False})
        response["traces"].append(evolve(MemoryRequest(**values), memory))
    return response

DECISIONS = {
    "WRITE_CURRENT": "通过写入门槛，保存为当前长期记忆。",
    "KEEP_SESSION_ONLY": "保留在工作层，未成为当前长期记忆；工作层仍存储在 SQLite 中。",
    "REINFORCED": "强化已有记忆，增加证据，不重复创建当前记忆。",
    "UNCHANGED": "该来源事件已处理，未重复写入或增加证据。",
    "CANDIDATE": "新证据进入候选区，暂不替换当前记忆。",
    "CONSOLIDATED": "证据门控通过，新记忆成为当前，旧记忆转为历史。",
    "DROP": "隐私门拦截，未保存记忆正文。",
}


class EvolutionStorage:
    def __init__(self, storage):
        self.storage = storage
        self.events = []
        self.previous = None

    def __getattr__(self, name):
        return getattr(self.storage, name)

    def find_duplicate(self, user_id, normalized, memory_key=None, memory_type=None):
        record = self.storage.find_duplicate(user_id, normalized, memory_key, memory_type)
        if record:
            self.previous = dict(record)
        return record

    def find_current(self, user_id, memory_key):
        record = self.storage.find_current(user_id, memory_key)
        if record:
            self.previous = dict(record)
        return record

    def audit(self, user_id, event_type, message, memory_id=None, details=None):
        self.storage.audit(user_id, event_type, message, memory_id, details)
        self.events.append({
            "event_type": event_type,
            "message": message,
            "memory_id": memory_id,
            "details": details or {},
        })


class EvolutionEncoder:
    def __init__(self, encoder):
        self.encoder = encoder
        self.values = {}

    def __getattr__(self, name):
        return getattr(self.encoder, name)

    def attention_profile(self, *args, **kwargs):
        values = self.encoder.attention_profile(*args, **kwargs)
        self.values.update(zip(
            ("saliency", "goal_relevance", "preference_strength", "attention_bias"),
            values,
        ))
        return values

    def write_score(self, *args, **kwargs):
        value = self.encoder.write_score(*args, **kwargs)
        self.values["write_score"] = value
        return value


@router.post("", status_code=201)
def evolve(payload: MemoryRequest, memory: MemoryDependency):
    storage = EvolutionStorage(memory.storage)
    observer = Memory(config=memory.config, storage=storage)
    encoder = EvolutionEncoder(observer.encoder)
    observer.encoder = encoder
    result = observer.add_memory(payload.model_dump(exclude_unset=True))
    record = result.get("memory")
    decision = result["decision"]
    replayed = decision == "UNCHANGED"
    duplicate = result.get("reason") in {"exact_duplicate", "source_event_already_processed"}
    dropped = decision == "DROP"
    encoded = not dropped and not duplicate
    compared = encoded and decision != "KEEP_SESSION_ONLY"
    score_fields = [
        ("saliency", "显著性"),
        ("goal_relevance", "任务相关性"),
        ("preference_strength", "偏好强度"),
        ("attention_bias", "注意偏向"),
        ("write_score", "写入分数"),
    ]
    encoding_fields = [
        {"label": label, "value": round(encoder.values[field], 4)}
        for field, label in score_fields
    ] if encoded else []
    if encoded:
        encoding_fields.append({"label": "写入门槛", "value": memory.config.write_threshold})
    comparison_fields = []
    for event in storage.events:
        if event["event_type"] == "CANDIDATE":
            comparison_fields = [
                {"label": "预测误差", "value": event["details"]["cpe"]},
                {"label": "一致证据数量", "value": event["details"]["evidence_count"]},
                {"label": "证据一致性", "value": event["details"]["consistency"]},
                {"label": "巩固误差门槛", "value": memory.config.cpe_commit_threshold},
                {"label": "最低证据数量", "value": memory.config.minimum_evidence_count},
                {"label": "一致性门槛", "value": memory.config.evidence_consistency_threshold},
                {"label": "取值明确变化", "value": event["details"].get("explicit_value_change", False)},
            ]
    privacy_message = {
        "do_not_store_instruction": "识别到不记忆指令，未保存正文。",
        "consent_required": "敏感标签缺少明确保存同意，未保存正文。",
    }.get(result.get("reason"), "通过隐私门；同一用户范围内检查重复、类型和写入价值。")
    comparison_message = (
        "来源事件已处理，本次不重新比较，也不增加证据。" if replayed
        else "发现完全重复的正文，直接强化已有记录，跳过评分与冲突巩固。" if duplicate
        else "未执行长期记忆比较。" if not compared
        else "找到相同记忆键的当前记录，比较新旧值。" if storage.previous
        else "未找到可比较的当前记录。" if payload.memory_key.strip()
        else "未提供记忆键，不执行同主题新旧值比较。"
    )
    return {
        "result": result,
        "previous": storage.previous,
        "events": storage.events,
        "config": asdict(memory.config),
        "steps": [
            {"title": "原始输入", "status": "done", "description": "进入记忆引擎的原文证据和结构化字段。", "fields": [
                {"label": "原文", "value": payload.content.strip()},
                {"label": "用户", "value": record["user_id"] if record else payload.user_id},
                {"label": "记忆键", "value": payload.memory_key or "未指定"},
                {"label": "记忆值", "value": payload.memory_value or "未指定"},
            ]},
            {"title": "选择性编码", "status": "blocked" if dropped else "skipped" if duplicate else "done", "description": "来源事件已处理，跳过重复编码，不增加证据。" if replayed else privacy_message if not duplicate else "完全重复输入直接强化，不重新进行类型与评分计算。", "fields": encoding_fields},
            {"title": "新旧比较", "status": "done" if compared or duplicate else "skipped", "description": comparison_message, "fields": comparison_fields},
            {"title": "巩固决策", "status": "blocked" if dropped else "done", "description": DECISIONS[decision], "fields": [{"label": "决策代码", "value": decision}, {"label": "原因代码", "value": result.get("reason", "")}]},
            {"title": "存储结果", "status": "blocked" if dropped else "done", "description": "未创建记忆正文记录，仅保留既有隐私审计。" if dropped else "返回 SQLite 中的实际记录。类型与生命周期状态分别展示。", "fields": []},
        ],
    }
