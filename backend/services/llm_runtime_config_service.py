from services.model_capability_service import ModelCapabilityService
from schemas.execution_config_schemas import ExecutionConfig
from schemas.model_capabilities_schemas import ModelCapabilities
from schemas.runtime_llm_config_schemas import RuntimeLLMConfig

class LLMRuntimeConfigService:
    def build(
            self,
            provider: str,
            execution_config: ExecutionConfig,
            capabilities: ModelCapabilities,
    ) -> RuntimeLLMConfig:
        return RuntimeLLMConfig(
            provider=provider.lower(),

            supports_reasoning=capabilities.supports_reasoning,
            supports_temperature=capabilities.supports_temperature,

            reasoning_level=execution_config.reasoning_level,
            reasoning_parameter=capabilities.reasoning_parameter,
            reasoning_profile_map=capabilities.reasoning_profile_map,

            agent_limits={
                "max_iterations": execution_config.max_iterations,
                "max_retrieval_calls": execution_config.max_retrieval_calls
            }
        )