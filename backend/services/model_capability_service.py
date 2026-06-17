from schemas.model_capabilities_schemas import ModelCapabilities

class ModelCapabilityService:
    def get_capabilities(
            self,
            provider: str,
    ) -> ModelCapabilities:
        # De forma temporal para poder probar la funcion
        if provider.lower() == "openai":
            return ModelCapabilities(
                supports_reasoning=True,
                supports_reasoning_effort=True,
                supports_tools=True,
                supports_multimodal=True,
            )
        
        if provider.lower() == "google":
            return ModelCapabilities(
                supports_reasoning=True,
                supports_thinking_budget=True,
                supports_tools=True,
                supports_multimodal=True,
            )
        
        return ModelCapabilities()
