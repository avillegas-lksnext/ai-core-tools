from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime
import enum

class ChangeType(str, enum.Enum):
    """Type of configuration change"""
    CREATE = "create"
    UPDATE = "update"
    RESTORE = "restore"
    PROMPT_UPDATE = "prompt_update"
    SKILL_CHANGE = "skill_change"
    TOOL_CHANGE = "tool_change"
    MCP_CHANGE = "mcp_change"

class ConfigAuditLog(Base):
    __tablename__ = "config_audit_log"

    audit_id = Column(Integer, primary_key=True)
    config_id = Column(Integer, ForeignKey("AgentConfigVersion.config_id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("Agent.agent_id", ondelete="CASCADE"), nullable=False, index=True)
    app_id = Column(Integer, ForeignKey("App.app_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Change tracking
    change_type = Column(SQLEnum(ChangeType, name="changetype", values_callable=lambda enum: [e.value for e in enum]), nullable=False)
    changed_by_user_id = Column(Integer, ForeignKey("User.user_id", ondelete="SET NULL"), nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # What changed (field name and old/new values)
    field_name = Column(String(255), nullable=True)  # e.g., 'system_prompt', 'allowed_tools'
    old_value = Column(Text, nullable=True)          # JSON string
    new_value = Column(Text, nullable=True)          # JSON string
    
    # Context
    change_reason = Column(String(1024), nullable=True)  # Why was this changed?
    related_config_id = Column(Integer, nullable=True)   # If restore, the old config_id
    
    # Relationships
    agent_config_version = relationship("AgentConfigVersion", back_populates="audit_logs")
    
    def __repr__(self):
        return f"<ConfigAuditLog agent_id={self.agent_id} change_type={self.change_type} at={self.changed_at}>"