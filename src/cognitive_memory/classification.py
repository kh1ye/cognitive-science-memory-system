"""Long-term content types, independent of lifecycle/storage roles."""

from .enums import MEMORY_TYPES


def infer_memory_type(tags: list[str], requested: str | None = None) -> str:
    if requested is not None and requested != "":
        if requested not in MEMORY_TYPES:
            raise ValueError("memory_type 仅支持 episodic、semantic、procedural")
        return requested
    tag_set = set(tags)
    if tag_set & {"procedure", "workflow", "流程", "工作流"}:
        return "procedural"
    if tag_set & {"profile", "preference", "goal", "fact", "画像", "偏好", "目标"}:
        return "semantic"
    if tag_set & {"event", "timeline", "tool", "事件", "时间线", "工具"}:
        return "episodic"
    return "semantic"
