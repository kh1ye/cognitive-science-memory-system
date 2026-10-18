"""Environment-configured LangChain model; no network access during startup."""

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
