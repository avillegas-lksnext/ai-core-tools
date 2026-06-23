from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session

from models.agent import Agent
from models.agent_config_version import AgentConfigVersion


class AgentRegistryService:
    @staticmethod
    def _derive_memory_scope(agent: Agent) -> str:
        return "session" if bool(getattr(agent, "has_memory", False)) else "none"

    @staticmethod
    def get_active_config(db: Session, agent_id: int) -> Optional[AgentConfigVersion]:
        return (
            db.query(AgentConfigVersion)
            .filter(
                AgentConfigVersion.agent_id == agent_id,
                AgentConfigVersion.is_active.is_(True),
            )
            .order_by(AgentConfigVersion.version_number.desc())
            .first()
        )

    @staticmethod
    def ensure_initial_version(
        db: Session,
        agent: Agent,
        created_by_user_id: int | None = None,
    ) -> AgentConfigVersion:
        existing = (
            db.query(AgentConfigVersion)
            .filter(AgentConfigVersion.agent_id == agent.agent_id)
            .order_by(AgentConfigVersion.version_number.desc())
            .first()
        )
        if existing:
            return existing

        config = AgentConfigVersion(
            agent_id=agent.agent_id,
            version_number=1,
            is_active=True,
            system_prompt=agent.system_prompt or "",
            persona=None,
            domain=None,
            tone=None,
            constraints=[],
            allowed_tools=getattr(agent, "server_tools", None) or [],
            memory_scope=AgentRegistryService._derive_memory_scope(agent),
            created_by_user_id=created_by_user_id,
        )
        db.add(config)
        db.flush()
        return config

    @staticmethod
    def backfill_missing_versions(db: Session) -> int:
        agents = db.query(Agent).all()
        created = 0

        for agent in agents:
            exists = (
                db.query(AgentConfigVersion.config_id)
                .filter(AgentConfigVersion.agent_id == agent.agent_id)
                .first()
            )
            if exists:
                continue

            db.add(
                AgentConfigVersion(
                    agent_id=agent.agent_id,
                    version_number=1,
                    is_active=True,
                    system_prompt=agent.system_prompt or "",
                    persona=None,
                    domain=None,
                    tone=None,
                    constraints=[],
                    allowed_tools=getattr(agent, "server_tools", None) or [],
                    memory_scope=AgentRegistryService._derive_memory_scope(agent),
                    created_by_user_id=None,
                )
            )
            created += 1

        db.flush()
        return created