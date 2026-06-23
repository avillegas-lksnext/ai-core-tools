from datetime import datetime
from sqlalchemy import (Column, Integer, String, Text, Boolean, ForeignKey, DateTime, JSON, UniqueConstraint)
from sqlalchemy.orm import relationship

from db.database import Base

class AgentConfigVersion(Base):
    __tablename__ = "AgentConfigVersion"

    config_id = Column(Integer, primary_key=True)
    agent_id = Column(
        Integer,
        ForeignKey('Agent.agent_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True, server_default='true')

    # Immutable identity layer
    system_prompt = Column(Text, nullable=False, default='', server_default='')
    persona = Column(String(500), nullable=True)
    domain = Column(String(255), nullable=True)
    tone = Column(String(255), nullable=True)
    constraints = Column(JSON, nullable=False, default=list, server_default='[]')
    allowed_tools = Column(JSON, nullable=False, default=list, server_default='[]')
    memory_scope = Column(String(20), nullable=False, default='none', server_default='none')

    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by_user_id = Column(Integer, ForeignKey('User.user_id'), nullable=True)

    agent = relationship(
        'Agent',
        foreign_keys=[agent_id],
        back_populates='config_versions',
    )

    __table_args__ = (
        UniqueConstraint('agent_id', 'version_number', name='uq_agent_config_version'),
    )