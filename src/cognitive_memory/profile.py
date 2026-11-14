"""Read-only user modelling over Current semantic assertions; no profile storage."""
from dataclasses import asdict, dataclass, field
import json

from .keys import canonicalize_memory_key
from .models import iso_now
from .retrieval.lexical import normalize_text

# Form keys map to the same topics used by conversational learning.
PREFERENCE_FIELDS = {
    "name": ("preferred_name", "称呼", "identity"),
    "language": ("preferred_language", "交流语言", "interaction"),
    "style": ("response_style", "回答风格", "interaction"),
    "interests": ("interests", "兴趣", "interests"),
    "tools": ("common_tools", "常用工具", "skills"),
    "notes": ("interaction_notes", "其他偏好", "interaction"),
}
TOPICS = {
    "identity": {"preferred_name", "name", "nickname", "occupation", "profession", "job_title", "education", "location", "称呼", "姓名", "职业", "身份"},
    "interaction": {"preferred_language", "language", "response_language", "communication_language", "response_style", "communication_style", "answer_style", "interaction_notes", "交流语言", "回答风格", "交互偏好"},
    "interests": {"interests", "interest", "hobbies", "hobby", "preferred_beverage", "favorite_food", "兴趣", "爱好"},
    "skills": {"common_tools", "tools", "preferred_tools", "preferred_programming_language", "skills", "skill", "expertise", "常用工具", "技能", "编程语言"},
    "goals": {"long_term_goal", "long_term_goals", "goal", "goals", "career_goal", "长期目标", "目标"},
}
FIELD_ALIASES = {"name": {"preferred_name", "name", "nickname", "称呼", "姓名"},
    "language": TOPICS["interaction"] & {"preferred_language", "language", "response_language", "communication_language", "交流语言"},
    "style": {"response_style", "communication_style", "answer_style", "回答风格"},
    "interests": {"interests", "interest", "hobbies", "hobby", "兴趣", "爱好"},
    "tools": {"common_tools", "tools", "preferred_tools", "常用工具"},
    "notes": {"interaction_notes"}}


def dimension_for(predicate, tags):
    for dimension, topics in TOPICS.items():
        if predicate in topics:
            return dimension
    # Extraction predicates are open vocabulary (e.g. 喜欢的运动/爱好).
    for dimension, cues in (("goals", ("长期目标", "计划", "目标")),
                            ("interaction", ("交流", "回答", "语言", "沟通")),
                            ("skills", ("技能", "工具", "编程")),
                            ("interests", ("兴趣", "爱好", "喜欢", "运动"))):
        if any(cue in (predicate or "") for cue in cues):
            return dimension
    # Tags are explicit memory-engine metadata, not inferred personality traits.
    for dimension, cues in (("goals", {"goal", "长期目标"}), ("interests", {"interest", "hobby", "兴趣"}),
                            ("skills", {"skill", "expertise", "tool", "技能"}),
                            ("interaction", {"preference", "communication", "偏好"}), ("identity", {"profile", "身份"})):
        if set(tags) & cues:
            return dimension
    return "personal"


def describe_personal_fact(predicate, value, evidence):
    """Render a grounded statement, not an inferred personality judgement."""
    openings = ("我喜欢", "我习惯", "我常用", "我主要", "我是", "我希望", "我计划", "我正在", "我擅长")
    if evidence.startswith(openings):
        return "你" + evidence[1:]
    templates = {"preferred_name": "你希望被称呼为{value}", "preferred_language": "你偏好使用{value}交流",
                 "response_style": "你喜欢的回答风格是：{value}", "common_tools": "你常用的工具包括：{value}",
                 "interests": "你的兴趣包括：{value}", "preferred_programming_language": "你偏好的编程语言是{value}"}
    if predicate in templates:
        return templates[predicate].format(value=value)
    return f"你曾提到：“{evidence}”" if evidence else f"你提到的{predicate}：{value}"


@dataclass
class UserProfile:
    user_id: str
    items: list[dict] = field(default_factory=list)

    @classmethod
    def read(cls, memory, user_id):
        user = normalize_text(user_id) or "demo-user"
        items = []
        with memory.storage.transaction():
            for row in memory.architecture.repo.rows("semantic_assertions", user, "user"):
                policy = row.get("_policy", {})
                if (policy.get("state_role") != "current" or row.get("status") != "current"
                    or row.get("subject") != user or row.get("epistemic_status") not in ("explicit", "supported")
                    or (row.get("valid_from") and row["valid_from"] > iso_now())
                    or (row.get("valid_to") and row["valid_to"] <= iso_now())):
                    continue
                predicate = canonicalize_memory_key(row.get("predicate"))
                tags = json.loads(policy.get("tags_json") or "[]")
                dimension = dimension_for(predicate, tags)
                # Respect the engine's consent gate even for imported/native records.
                sources = [memory.architecture.repo.get("source_records", user, ref) for ref in row.get("source_refs", [])]
                if row.get("sensitive") or set(tags) & {"sensitive", "private", "敏感", "隐私"}:
                    if not row.get("metadata", {}).get("consent") and (not sources or any(not source or not source.get("consent") for source in sources)):
                        continue
                value = row.get("value")
                text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                if not text or value is None:
                    continue
                items.append({"id": row["id"], "dimension": dimension, "predicate": predicate,
                    "value": text, "description": describe_personal_fact(predicate, text, row.get("evidence_text") or row.get("content") or ""),
                    "evidence_text": row.get("evidence_text") or row.get("content") or "", "state_role": "current", "source_refs": row.get("source_refs", []),
                    "updated_at": row.get("updated_at") or row.get("recorded_at"),
                    "confidence": row.get("confidence", .8)})
        return cls(user, sorted(items, key=lambda item: (item["updated_at"] or "", item["id"]), reverse=True))

    def to_dict(self):
        preferences = {}
        for key, aliases in FIELD_ALIASES.items():
            preferences[key] = next((item["value"] for item in self.items if item["predicate"] in aliases), "")
        return {**asdict(self), "preferences": preferences}

    def context(self, max_chars=4000):
        """Bound the entire serialized profile without truncating a JSON document."""
        result = []
        # Core communication/identity first, followed by the remaining dimensions.
        for item in sorted(self.items, key=lambda item: (item["dimension"] not in ("identity", "interaction"))):
            compact = {key: item[key] for key in ("id", "dimension", "predicate", "value")}
            if len(json.dumps(result + [compact], ensure_ascii=False)) <= max_chars:
                result.append(compact)
        return result


def save_preferences(memory, user_id, values, *, consent=False):
    """Explicit edits use the engine; the view owns no lifecycle or write policy."""
    user = normalize_text(user_id) or "demo-user"
    with memory.storage.transaction():
        for field_name, value in values.items():
            key, label, dimension = PREFERENCE_FIELDS[field_name]
            aliases = FIELD_ALIASES[field_name]
            current = UserProfile.read(memory, user)
            ids = [item["id"] for item in current.items if item["predicate"] in aliases]
            if len(ids) == 1 and next(item["value"] for item in current.items if item["id"] == ids[0]) == value.strip():
                continue
            if not value.strip():
                for mid in ids:
                    memory.delete_memory(user, mid)
                continue
            memory.edit_semantic_memory(user, key, value.strip(), f"我的{label}：{value.strip()}",
                tags=["profile", "preference"] if dimension == "interaction" else ["profile", {"skills": "skill", "interests": "interest"}.get(dimension, "profile")],
                replace_ids=ids, consent=consent)
    return UserProfile.read(memory, user)
