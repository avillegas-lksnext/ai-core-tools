from schemas.execution_config_schemas import ExecutionConfig
from schemas.provider_execution_config_schemas import ProviderExecutionConfig
from schemas.model_capabilities_schemas import ModelCapabilities

class ProviderExecutionResolver:
    def resolve(
            self,
            execution_config: ExecutionConfig,
            capabilities: ModelCapabilities,
    ) -> ProviderExecutionConfig:
        provider_config = ProviderExecutionConfig()

        if capabilities.supports_reasoning_effort:
            effort_map = {
                0: "minimal",
                1: "low",
                2: "medium",
                3: "high",
            }

            provider_config.reasoning_effort = effort_map[execution_config.reasoning_level]
        
        if capabilities.supports_thinking_budget:
            budget_map = {
                0: 1024,
                1: 4096,
                2: 8192,
                3: 16384,
            }

            provider_config.thinking_budget = budget_map[execution_config.reasoning_level]
        
        provider_config.max_tool_calls = execution_config.max_tool_calls
        provider_config.max_retrieval_calls = execution_config.max_retrieval_calls

        return provider_config