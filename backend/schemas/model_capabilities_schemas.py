from pydantic import BaseModel

class ModelCapabilities(BaseModel):
    provider: str

    supports_reasoning: bool = False
    supports_reasoning_effort: bool = False
    supports_thinking_budget: bool = False

    supports_temperature: bool = True
    supports_tools: bool = True
    supports_multimodal: bool = False