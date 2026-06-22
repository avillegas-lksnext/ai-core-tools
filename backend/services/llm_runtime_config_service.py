from schemas.execution_config_schemas import ExecutionConfig
from schemas.model_capabilities_schemas import ModelCapabilities
from schemas.runtime_llm_config_schemas import RuntimeLLMConfig

class LLMRuntimeConfigService:
    def build(
            self,
            provider: str,
            execution_config: ExecutionConfig,
            capabilities: ModelCapabilities
    ) -> RuntimeLLMConfig:
        return RuntimeLLMConfig(
            provider=provider.lower(),
            reasoning_level=execution_config.reasoning_level,
            supports_reasoning_effort=capabilities.supports_reasoning_effort,
            supports_thinking_budget=capabilities.supports_thinking_budget,
            agent_limits={
                "max_iterations": execution_config.max_iterations,
                "max_retrieval_calls": execution_config.max_retrieval_calls
            }
        )