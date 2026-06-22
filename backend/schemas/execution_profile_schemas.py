    

from enum import Enum
from pydantic import BaseModel


class ExecutionProfileType(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    MAX = "max"

class ExecutionProfile(BaseModel):
    id: ExecutionProfileType
    label: str
    reasoning_level: int
    tool_usage_level: int
    retrieval_level: int