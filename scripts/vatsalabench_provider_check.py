"""Check provider connectivity without uploading dataset content."""
import json
from datetime import datetime
from pathlib import Path
from conversation_agent.llm import LLMSettings

s = LLMSettings.from_env()
try:
    response = s.create_model().bind(max_tokens=16).invoke("Reply only OK")
    result = {"success": True, "answer": response.text, "metadata": response.response_metadata}
except Exception as error:
    result = {"success": False, "error_type": type(error).__name__,
              "status_code": getattr(error, "status_code", None),
              "message": str(error).replace(s.api_key, "[REDACTED]") if s.api_key else str(error)}
output = Path("evaluation/Vatsalabench/results") / datetime.now().strftime("provider-check-%Y%m%d-%H%M%S-%f") / "result.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
