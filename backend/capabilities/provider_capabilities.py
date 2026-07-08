from schemas.model_capabilities_schemas import ModelCapabilities

PROVIDER_CAPABILITIES = {
    "openai": ModelCapabilities(
        provider="openai",
        supports_reasoning=False,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=True,

        reasoning_parameter="reasoning_effort",
        reasoning_profile_map={
            0: None,
            1: "low",
            2: "medium",
            3: "high",
        },
    ),

    "azure": ModelCapabilities(
        provider="azure",
        supports_reasoning=False,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=True,

        reasoning_parameter="reasoning_effort",
        reasoning_profile_map={
            0: None,
            1: "low",
            2: "medium",
            3: "high",
        },
    ),

    "anthropic": ModelCapabilities(
        provider="anthropic",
        supports_reasoning=True,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=True,

        reasoning_parameter="thinking_budget",
        reasoning_profile_map={
            0: 1024,
            1: 4096,
            2: 8192,
            3: 16384,
        },
    ),

    "google": ModelCapabilities(
        provider="google",
        supports_reasoning=True,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=True,

        reasoning_parameter="thinking_budget",
        reasoning_profile_map={
            0: 1024,
            1: 4096,
            2: 8192,
            3: 16384,
        },
    ),

    "googlecloud": ModelCapabilities(
        provider="googlecloud",
        supports_reasoning=True,
        supports_temperature=True,
        supports_tools=True,
        supports_multimodal=True,

        reasoning_parameter="thinking_budget",
        reasoning_profile_map={
            0: 1024,
            1: 4096,
            2: 8192,
            3: 16384,
        },
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