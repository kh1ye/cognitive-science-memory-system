"""User profile is a projection of engine-owned Current semantic memory."""
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from cognitive_memory.profile import UserProfile, save_preferences
from ..dependencies import MemoryDependency
from ..responses import error_response
from ..schemas import SessionRequest

router = APIRouter(prefix="/api/profile", tags=["profile"])


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(default="", max_length=500)
    language: str = Field(default="", max_length=500)
    style: str = Field(default="", max_length=500)
    interests: str = Field(default="", max_length=500)
    tools: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=2000)


class ProfileSettings(SessionRequest):
    preferences: Preferences
    consent: bool = False


class ProfileEdit(SessionRequest):
    value: str = Field(min_length=1, max_length=2000)
    consent: bool = False


@router.get("")
def get_profile(memory: MemoryDependency, user_id: str = "demo-user"):
    return UserProfile.read(memory, user_id).to_dict()


@router.put("")
def update_preferences(payload: ProfileSettings, memory: MemoryDependency):
    return save_preferences(memory, payload.user_id,
        payload.preferences.model_dump(exclude_unset=True), consent=payload.consent).to_dict()


@router.patch("/{memory_id}")
def edit_profile_item(memory_id: str, payload: ProfileEdit, memory: MemoryDependency):
    with memory.storage.transaction():
        item = next((item for item in UserProfile.read(memory, payload.user_id).items if item["id"] == memory_id), None)
        if item is None:
            return error_response("画像条目不存在", 404, "not_found")
        record = memory.storage.get_memory(memory_id)
        memory.edit_semantic_memory(payload.user_id, record["memory_key"], payload.value,
            f"我的{item['predicate']}：{payload.value}", tags=record["tags"],
            replace_ids=[memory_id], consent=payload.consent, predicate=item["predicate"])
        return UserProfile.read(memory, payload.user_id).to_dict()


@router.delete("/{memory_id}")
def delete_profile_item(memory_id: str, memory: MemoryDependency, user_id: str = "demo-user"):
    with memory.storage.transaction():
        profile = UserProfile.read(memory, user_id)
        if not any(item["id"] == memory_id for item in profile.items):
            return error_response("画像条目不存在", 404, "not_found")
        memory.delete_memory(profile.user_id, memory_id)
        return UserProfile.read(memory, profile.user_id).to_dict()
