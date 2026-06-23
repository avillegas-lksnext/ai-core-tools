    

from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class ExecutionProfileType(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    MAX = "max"

class ToolDepth(str, Enum):
    NONE = "none"
    LIGHT = "light"
    FULL = "full"

class ExecutionProfile(BaseModel):
    id: ExecutionProfileType
    label: str

    reasoning_level: int = Field(ge=0, le=3)
    tool_usage_level: int = Field(ge=0, le=3)
    retrieval_level: int = Field(ge=0, le=3)

    max_steps: int = Field(default=1, ge=1, le=20)
    tool_depth: ToolDepth = ToolDepth.NONE
    rag_enabled: bool = False
    latency_budget_ms: int = Field(default=5000, ge=1000, le=120000)
    cost_budget: float = Field(default=0.0, ge=0.0, le=1000.0)