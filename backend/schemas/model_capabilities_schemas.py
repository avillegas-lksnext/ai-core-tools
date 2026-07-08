from typing import Any, Dict
from pydantic import BaseModel

class ModelCapabilities(BaseModel):
    provider: str

    supports_reasoning: bool = False
    supports_temperature: bool = True
    supports_tools: bool = True
    supports_multimodal: bool = False

    reasoning_parameter: str | None = None
    reasoning_profile_map: Dict[int, Any] | None = None