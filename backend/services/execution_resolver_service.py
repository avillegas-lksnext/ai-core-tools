from schemas.execution_profile_schemas import ExecutionProfile
from schemas.execution_config_schemas import ExecutionConfig

from services.execution_profile_service import ITERATION_MAP, RETRIEVAL_MAP

class ExecutionResolverService:
    def resolve(
            self,
            profile: ExecutionProfile,
    ) -> ExecutionConfig:
        return ExecutionConfig(
            reasoning_level = profile.reasoning_level,
            max_iterations = ITERATION_MAP[profile.tool_usage_level],
            max_retrieval_calls = RETRIEVAL_MAP[profile.retrieval_level],
        )