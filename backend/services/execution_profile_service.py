from schemas.execution_profile_schemas import (
    ExecutionProfile,
    ExecutionProfileType,
    ResolvedExecutionSettings,
)

TOOL_MAP = {
    0: 1,  # FAST
    1: 3,  # BALANCED
    2: 10,  # DEEP
    3: 20,  # MAX
}

RETRIEVAL_MAP = {
    0: 1,  # FAST
    1: 2,  # BALANCED
    2: 4,  # DEEP
    3: 8,  # MAX
}

class ExecutionProfileService:
    _profiles = {
        ExecutionProfileType.FAST: ExecutionProfile(
            id=ExecutionProfileType.FAST,
            label="Fast",
            reasoning_level=0,
            tool_usage_level=0,
            retrieval_level=0
        ),
        ExecutionProfileType.BALANCED: ExecutionProfile(
            id=ExecutionProfileType.BALANCED,
            label="Balanced",
            reasoning_level=1,
            tool_usage_level=1,
            retrieval_level=1
        ),
        ExecutionProfileType.DEEP: ExecutionProfile(
            id=ExecutionProfileType.DEEP,
            label="Deep",
            reasoning_level=2,
            tool_usage_level=2,
            retrieval_level=2
        ),
        ExecutionProfileType.MAX: ExecutionProfile(
            id=ExecutionProfileType.MAX,
            label="Max",
            reasoning_level=3,
            tool_usage_level=3,
            retrieval_level=3
        ),
    }

    def get_profile(self, profile_type: ExecutionProfileType) -> ExecutionProfile:
        return self._profiles[profile_type]

    def get_default_profile(self) -> ExecutionProfile:
        return self._profiles[ExecutionProfileType.BALANCED]
    
    def resolve_profile(self, profile_type: str | None) -> ExecutionProfile:
        if not profile_type:
            return self.get_default_profile()
        
        try:
            return self.get_profile(ExecutionProfileType(profile_type))
        except ValueError:
            return self.get_default_profile()
    
    def build_execution_settings(self, profile: ExecutionProfile) -> ResolvedExecutionSettings:
        return ResolvedExecutionSettings(
            reasoning_level=profile.reasoning_level,
            max_tool_calls=TOOL_MAP[profile.tool_usage_level],
            max_retrieval_calls=RETRIEVAL_MAP[profile.retrieval_level]
        )
    
    def get_available_profiles(self) -> list[ExecutionProfile]:
        return list(self._profiles.values())
        
    