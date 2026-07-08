from typing import Any, Dict
from pydantic import BaseModel, Field


class RuntimeLLMConfig(BaseModel):
    provider: str

    supports_reasoning: bool = False
    supports_temperature: bool = True

    reasoning_level: int = 0
    reasoning_parameter: str | None = None
    reasoning_profile_map: Dict[int, Any] | None = None

    agent_limits: dict[str, int] = Field(default_factory=dict)