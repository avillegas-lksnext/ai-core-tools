from pydantic import BaseModel

class ExecutionConfig(BaseModel):
    reasoning_level: int
    max_tool_calls: int
    max_retrieval_calls: int