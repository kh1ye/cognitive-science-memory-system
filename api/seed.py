from __future__ import annotations

from typing import Any


def seed_demo(memory, user_id: str = "demo-user") -> list[dict[str, Any]]:
    memory.reset_user(user_id)
    events = [
        {
            "content": "用户长期编程偏好是 Python。",
            "memory_key": "coding_language",
            "memory_value": "Python",
            "memory_type": "semantic",
            "source": "user",
            "tags": ["profile", "preference"],
            "importance": 0.86,
            "confidence": 0.95,
        },
        {
            "content": "用户对花生严重过敏，规划餐饮时必须避开花生。",
            "memory_key": "food_allergy",
            "memory_value": "花生",
            "memory_type": "semantic",
            "source": "user",
            "tags": ["profile", "safety"],
            "importance": 1.0,
            "confidence": 0.98,
        },
        {
            "content": "用户最近更倾向使用 Rust 作为主要编程语言。",
            "memory_key": "coding_language",
            "memory_value": "Rust",
            "memory_type": "semantic",
            "source": "user_correction",
            "tags": ["preference", "conflict"],
            "importance": 0.9,
            "confidence": 0.92,
        },
        {
            "content": "用户再次确认未来项目主要使用 Rust。",
            "memory_key": "coding_language",
            "memory_value": "Rust",
            "memory_type": "semantic",
            "source": "user_feedback",
            "tags": ["preference", "conflict"],
            "importance": 0.9,
            "confidence": 0.94,
        },
        {
            "content": "演示流程：先运行测试，再启动服务，最后检查健康接口与浏览器页面。",
            "memory_key": "demo_workflow",
            "memory_value": "test-start-health-ui",
            "memory_type": "procedural",
            "source": "task_success",
            "tags": ["procedure", "workflow"],
            "importance": 0.82,
            "confidence": 0.9,
        },
    ]
    results = []
    for event in events:
        results.append(memory.add_memory({"user_id": user_id, **event}))
    return results
