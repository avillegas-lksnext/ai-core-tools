from schemas.model_capabilities_schemas import ModelCapabilities

PROVIDER_CAPABILITIES = {
    "openai": ModelCapabilities(
        provider="openai",
        supports_reasoning=False,
        supports_reasoning_effort=False,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=True,
    ),

    "azure": ModelCapabilities(
        provider="azure",
        supports_reasoning=False,
        supports_reasoning_effort=False,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=True,
    ),

    "anthropic": ModelCapabilities(
        provider="anthropic",
        supports_reasoning=True,
        supports_thinking_budget=True,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=True,
    ),

    "google": ModelCapabilities(
        provider="google",
        supports_reasoning=True,
        supports_thinking_budget=True,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=True,
    ),

    "googlecloud": ModelCapabilities(
        provider="googlecloud",
        supports_reasoning=True,
        supports_thinking_budget=True,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=True,
    ),

    "mistralai": ModelCapabilities(
        provider="mistralai",
        supports_reasoning=False,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=True,
    ),

    "custom": ModelCapabilities(
        provider="custom",
        supports_reasoning=False,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=False,
    ),
}