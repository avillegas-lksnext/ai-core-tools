from pydantic import BaseModel, Field


class RuntimeLLMConfig(BaseModel):
    provider: str
    reasoning_level: int = 0
    supports_reasoning_effort: bool = False
    supports_thinking_budget: bool = False
    agent_limits: dict[str, int] = Field(default_factory=dict)