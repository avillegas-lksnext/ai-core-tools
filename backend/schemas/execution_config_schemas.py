from pydantic import BaseModel

class ExecutionConfig(BaseModel):
    reasoning_level: int
    max_iterations: int
    max_retrieval_calls: int