from pydantic import BaseModel

class ProviderExecutionConfig(BaseModel):
    reasoning_effort: str | None = None
    thinking_budget: int | None = None
    max_tool_calls: int | None = None
    max_retrieval_calls: int | None = None