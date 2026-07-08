MODEL_CAPABILITIES = {

    "openai": {

        #
        # GPT-5-pro family
        #

        "gpt-5-pro": {
            "supports_reasoning": False,
            "supports_temperature": False,
        },

        "gpt-5.1-pro": {
            "supports_reasoning": False,
            "supports_temperature": False,
        },

        "gpt-5.2-pro": {
            "supports_reasoning": False,
            "supports_temperature": False,
        },

        "gpt-5.4-pro": {
            "supports_reasoning": False,
            "supports_temperature": False,
        },

        "gpt-5.5-pro": {
            "supports_reasoning": False,
            "supports_temperature": False,
        },

        #
        # Chat-latest
        #

        "gpt-5.1-chat-latest": {
            "supports_reasoning": True,
            "supports_temperature": False,
            "reasoning_profile_map": {
                0: "medium",
                1: "medium",
                2: "medium",
                3: "medium",
            },
        },

        "gpt-5.2-chat-latest": {
            "supports_reasoning": True,
            "supports_temperature": False,
            "reasoning_profile_map": {
                0: "medium",
                1: "medium",
                2: "medium",
                3: "medium",
            },
        },

        "gpt-5.3-chat-latest": {
            "supports_reasoning": True,
            "supports_temperature": False,
            "reasoning_profile_map": {
                0: "medium",
                1: "medium",
                2: "medium",
                3: "medium",
            },
        },

        #
        # Search API
        #

        "gpt-5-search-api": {
            "supports_reasoning": False,
            "supports_temperature": False,
        },

        "gpt-4o-search-preview": {
            "supports_reasoning": False,
            "supports_temperature": False,
        },

        "gpt-4o-mini-search-preview": {
            "supports_reasoning": False,
            "supports_temperature": False,
        },

        #
        # GPT-5 normal
        #

        "gpt-5.5": {
            "supports_reasoning": True,
        },

        "gpt-5.4": {
            "supports_reasoning": False,
        },

        "gpt-5.2": {
            "supports_reasoning": True,
        },

        "gpt-5.1": {
            "supports_reasoning": True,
        },

        "gpt-5": {
            "supports_reasoning": True,
            "reasoning_profile_map": {
                0: "minimal",
                1: "low",
                2: "medium",
                3: "high",
            },
        },

        #
        # o-series
        #

        "o1": {
            "supports_reasoning": True,
            "supports_temperature": False,
        },

        "o3": {
            "supports_reasoning": True,
            "supports_temperature": False,
        },

        "o4": {
            "supports_reasoning": True,
            "supports_temperature": False,
        },

        #
        # Computer use
        #

        "computer-use-preview": {
            "supports_reasoning": False,
            "supports_temperature": False,
        },
    },

    "azure": {

        "gpt-5": {
            "supports_reasoning": True,
            "reasoning_profile_map": {
                0: "minimal",
                1: "low",
                2: "medium",
                3: "high",
            },
        },

        "o1": {
            "supports_reasoning": True,
        },

        "o3": {
            "supports_reasoning": True,
        },

        "o4": {
            "supports_reasoning": True,
        },
    },

    "anthropic": {},

    "google": {},

    "googlecloud": {},

    "mistralai": {},

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