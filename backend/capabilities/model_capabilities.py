# Provider-scoped model capability overrides
# Structure: PROVIDER -> MODEL_PREFIX -> CAPABILITY_OVERRIDES

MODEL_CAPABILITIES = {

    "openai": {

        "gpt-5": {
            "supports_reasoning": True,
            "supports_reasoning_effort": True,
        },

        "o3": {
            "supports_reasoning": True,
            "supports_reasoning_effort": True,
        },

        "o4": {
            "supports_reasoning": True,
            "supports_reasoning_effort": True,
        },
    },

    "anthropic": {
    },

    "google": {
    },

    "googlecloud": {
    },

    "custom": {

        "deepseek-r1": {
            "supports_reasoning": True,
        },

        "qwq": {
            "supports_reasoning": True,
        },

        "qwen3": {
            "supports_reasoning": True,
        },
    },
}