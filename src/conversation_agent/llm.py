"""Environment-configured LangChain model; no network access during startup."""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values
from langchain_openai import ChatOpenAI


class ModelNotConfigured(RuntimeError):
    pass


class ChatModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMSettings:
    model: str = "gpt-4o-mini"
    api_key: str = field(default="", repr=False)
    base_url: str | None = None
    provider: str = "openai"

    @classmethod
    def from_env(cls):
        config = {
            **dotenv_values(
                Path(__file__).resolve().parents[2] / ".env", interpolate=False
            ),
            **os.environ,
        }
        return cls(
            model=config.get("LLM_MODEL", "gpt-4o-mini"),
            api_key=config.get("LLM_API_KEY") or config.get("OPENAI_API_KEY", ""),
            base_url=config.get("LLM_BASE_URL")
            or config.get("OPENAI_BASE_URL")
            or None,
            provider=config.get("LLM_PROVIDER", "openai").strip().lower(),
        )

    def create_model(self):
        if not self.api_key:
            raise ModelNotConfigured(
                "尚未配置 LLM_API_KEY，请配置模型环境变量后重启服务。"
            )
        if self.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=self.model,
                api_key=self.api_key,
                base_url=self.base_url,
                max_tokens=4096,
                timeout=45,
                max_retries=1,
            )
        if self.provider != "openai":
            raise ModelNotConfigured("LLM_PROVIDER 仅支持 openai 或 anthropic。")
        return ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=45,
            max_retries=1,
        )


def extract_memories(model, message):
    """Validate tool output, recovering JSON or requesting one format correction."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.output_parsers import JsonOutputParser

    from .prompts import EXTRACTION_PROMPT
    from .state import MemoryExtraction

    messages = [SystemMessage(content=EXTRACTION_PROMPT), HumanMessage(content=message)]
    try:
        response = model.with_structured_output(
            MemoryExtraction, method="function_calling", include_raw=True
        ).invoke(messages)
        if isinstance(response, MemoryExtraction):
            return response
        if "parsed" not in response:
            return MemoryExtraction.model_validate(response)
        if response["parsed"] is not None:
            return MemoryExtraction.model_validate(response["parsed"])
        raw = response.get("raw")
        if raw is not None and raw.text.strip():
            return MemoryExtraction.model_validate(JsonOutputParser().parse(raw.text))
    except Exception as error:  # noqa: BLE001 -- one independent recovery attempt
        logging.getLogger(__name__).info(
            "Retrying memory extraction after %s", type(error).__name__
        )
    schema = MemoryExtraction.model_json_schema()

    correction = SystemMessage(
        content=EXTRACTION_PROMPT
        + "\n上次结构化提取格式未通过校验。只输出符合以下 schema 的 JSON，不要解释。"
        + '没有新记忆时返回 {"memories": []}。\n'
        + json.dumps(schema, ensure_ascii=False)
    )
    response = model.invoke([correction, HumanMessage(content=message)])
    return MemoryExtraction.model_validate(JsonOutputParser().parse(response.text))
