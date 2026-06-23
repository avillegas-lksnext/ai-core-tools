"""
Schemas for agent config version endpoints.

Represents config history, audit trail, and version metadata.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AgentConfigVersionRead(BaseModel):
    """Response schema for a single config version."""
    
    config_id: int
    agent_id: int
    version_number: int
    is_active: bool
    system_prompt: str
    persona: Optional[str] = None
    domain: Optional[str] = None
    tone: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)
    allowed_tools: List[str] = Field(default_factory=list)
    memory_scope: str
    created_at: datetime
    created_by_user_id: Optional[int] = None

    model_config = {"from_attributes": True}


class AgentConfigHistoryResponse(BaseModel):
    """Response schema for config history endpoint."""
    
    agent_id: int
    versions: List[AgentConfigVersionRead] = Field(default_factory=list)


class ConfigVersionComparisonResponse(BaseModel):
    """Response schema for config version comparison."""
    
    version_1: Dict[str, Any]  # config_id, version_number, is_active, created_at
    version_2: Dict[str, Any]  # config_id, version_number, is_active, created_at
    differences: Dict[str, Dict[str, Any]]  # field_name -> {from, to}


class RestoreConfigResponse(BaseModel):
    """Response schema for config restore endpoint."""
    
    message: str
    old_version: int
    new_version: int
    new_config: AgentConfigVersionRead