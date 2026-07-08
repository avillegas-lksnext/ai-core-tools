from copy import deepcopy

from capabilities.provider_capabilities import PROVIDER_CAPABILITIES
from capabilities.model_capabilities import MODEL_CAPABILITIES
from schemas.model_capabilities_schemas import ModelCapabilities
from schemas.execution_profile_schemas import ExecutionProfileType
from utils.logger import get_logger

logger = get_logger(__name__)


class ModelCapabilityService:
    def get_capabilities(
        self,
        provider: str,
        model_name: str,
    ) -> ModelCapabilities:
        provider_key = (provider or "").lower()
        model_key = (model_name or "").lower()

        # Get base provider capabilities, with safe fallback
        base = PROVIDER_CAPABILITIES.get(provider_key)
        if base is None:
            logger.warning(
                "Unknown provider '%s'; creating basic capabilities object",
                provider,
            )
            base = ModelCapabilities(provider=provider_key or "unknown")

        capabilities = deepcopy(base)

        # Apply provider-scoped model overrides
        provider_models = MODEL_CAPABILITIES.get(provider_key, {})
        for prefix, overrides in sorted(provider_models.items(), key=lambda x: len(x[0]), reverse=True):
            if model_key.startswith(prefix.lower()):
                logger.info(
                    "Applying model capability overrides for %s model %s (prefix: %s)",
                    provider,
                    model_name,
                    prefix,
                )
                for key, value in overrides.items():
                    setattr(capabilities, key, value)
                break

        return capabilities
    
    def get_reasoning_effort(
            self, provider: str,
            model_name: str,
            execution_profile: ExecutionProfileType | str,
    ) -> str | None:
        capabilities = self.get_capabilities(provider, model_name)

        if not capabilities.supports_reasoning_effort:
            return None
        
        if capabilities.reasoning_effort_mapping is None:
            return None
        
        profile = (
            execution_profile.value
            if isinstance(execution_profile, ExecutionProfileType)
            else execution_profile
        )

        return capabilities.reasoning_effort_mapping.get(profile.upper())