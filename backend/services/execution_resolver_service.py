from schemas.execution_profile_schemas import ExecutionProfile
from schemas.execution_config_schemas import ExecutionConfig

class ExecutionResolverService:
    def resolve(
            self,
            profile: ExecutionProfile,
    ) -> ExecutionConfig:
        tool_limits = {
            0: 1,
            1: 3,
            2: 10,
            3: 20,
        }

        retrieval_limits = {
            0: 1,
            1: 2,
            2: 4,
            3: 8,
        }

        return ExecutionConfig(
            reasoning_level = profile.reasoning_level,
            max_tool_calls = tool_limits[profile.tool_usage_level],
            max_retrieval_calls = retrieval_limits[profile.retrieval_level],
        )