from copy import deepcopy

from capabilities.provider_capabilities import PROVIDER_CAPABILITIES
from capabilities.model_capabilities import MODEL_CAPABILITIES
from schemas.model_capabilities_schemas import ModelCapabilities
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
        for prefix, overrides in provider_models.items():
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