from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, Any

class ConfigAuditLogRead(BaseModel):
    """Response model for audit log entry."""
    model_config = ConfigDict(from_attributes=True)
    
    audit_id: int
    config_id: int
    agent_id: int
    change_type: str
    changed_at: datetime
    changed_by_user_id: Optional[int] = None
    field_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    change_reason: Optional[str] = None
    related_config_id: Optional[int] = None

class ConfigAuditHistoryResponse(BaseModel):
    """Container for audit history for a config version."""
    config_id: int
    total_entries: int
    audit_logs: list[ConfigAuditLogRead]

class AgentAuditHistoryResponse(BaseModel):
    """Container for complete audit history for an agent."""
    agent_id: int
    total_entries: int
    audit_logs: list[ConfigAuditLogRead]

class FieldChangeHistoryResponse(BaseModel):
    """Container for changes to a specific field."""
    agent_id: int
    field_name: str
    total_entries: int
    changes: list[ConfigAuditLogRead]