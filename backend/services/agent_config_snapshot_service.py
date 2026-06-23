"""
AgentConfigSnapshotService — manage config version lifecycle.

Handles creating immutable snapshots of agent configuration state,
retrieving history, and restoring prior versions.
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy import desc
from sqlalchemy.orm import Session
from models.agent import Agent
from models.agent_config_version import AgentConfigVersion
from models.config_audit_log import ChangeType
from services.config_audit_service import ConfigAuditService

class AgentConfigSnapshotService:
    """Service for managing agent config version snapshots and history."""

    @staticmethod
    def create_snapshot(
        db: Session,
        agent: Agent,
        created_by_user_id: int | None = None,
        change_reason: str = None
    ) -> AgentConfigVersion:
        """
        Create a new config version snapshot.
        
        Args:
            db: Database session
            agent: Fresh agent instance with current state
            created_by_user_id: User ID who created this snapshot
            change_reason: Optional reason for this snapshot (e.g., "Updated system prompt for v2")
        
        Returns:
            New AgentConfigVersion instance
        """
        # Fetch fresh agent to ensure we have latest state
        current_agent = db.query(Agent).filter(Agent.agent_id == agent.agent_id).first()
        if not current_agent:
            raise ValueError(f"Agent {agent.agent_id} not found")

        # Get next version number
        max_version = (
            db.query(AgentConfigVersion.version_number)
            .filter(AgentConfigVersion.agent_id == agent.agent_id)
            .order_by(desc(AgentConfigVersion.version_number))
            .first()
        )
        next_version = (max_version[0] + 1) if max_version else 1

        # Deactivate prior active version (if any)
        db.query(AgentConfigVersion).filter(
            AgentConfigVersion.agent_id == agent.agent_id,
            AgentConfigVersion.is_active.is_(True),
        ).update({AgentConfigVersion.is_active: False})

        # Create new active snapshot
        snapshot = AgentConfigVersion(
            agent_id=agent.agent_id,
            version_number=next_version,
            is_active=True,
            system_prompt=current_agent.system_prompt or "",
            persona=None,  # v0: persona not yet captured at agent level
            domain=None,    # v0: domain not yet captured at agent level
            tone=None,      # v0: tone not yet captured at agent level
            constraints=[],  # v0: constraints not yet captured at agent level
            allowed_tools=getattr(current_agent, "server_tools", None) or [],
            memory_scope="session" if current_agent.has_memory else "none",
            created_by_user_id=created_by_user_id,
        )
        db.add(snapshot)
        db.flush()

        # Log the snapshot creation
        ConfigAuditService.log_change(
            db=db,
            agent_id=agent.agent_id,
            app_id=current_agent.app_id,
            config_id=snapshot.config_id,
            change_type=ChangeType.CREATE,
            changed_by_user_id=created_by_user_id,
            change_reason=change_reason or "Config version snapshot created",
        )

        return snapshot
    
    @staticmethod
    def get_history(
        db: Session,
        agent_id: int,
        limit: int = 50,
    ) -> List[AgentConfigVersion]:
        """
        Get config version history for an agent (newest first).
        
        Args:
            db: Database session
            agent_id: Agent ID
            limit: Max versions to return (default 50)
        
        Returns:
            List of AgentConfigVersion, ordered by version_number descending
        """
        return (
            db.query(AgentConfigVersion)
            .filter(AgentConfigVersion.agent_id == agent_id)
            .order_by(desc(AgentConfigVersion.version_number))
            .limit(limit)
            .all()
        )
    
    @staticmethod
    def get_version(
        db: Session,
        config_id: int,
    ) -> Optional[AgentConfigVersion]:
        """
        Fetch a specific config version by config_id.
        
        Args:
            db: Database session
            config_id: Config version ID
        
        Returns:
            AgentConfigVersion or None if not found
        """
        return db.query(AgentConfigVersion).filter(
            AgentConfigVersion.config_id == config_id
        ).first()
    
    @staticmethod
    def restore_version(
        db: Session,
        config_id: int,
        created_by_user_id: int | None = None,
        change_reason: str = None,
    ) -> AgentConfigVersion:
        """
        Restore a prior config version by creating a new snapshot from it.
        
        Reads the old version, creates a new version (incremented number)
        with its values, and marks the old version as inactive.
        
        Args:
            db: Database session
            config_id: Config version ID to restore from
            created_by_user_id: User ID for audit trail
            change_reason: Optional reason for the restore
        
        Returns:
            New AgentConfigVersion with copied values and incremented version_number
        
        Raises:
            ValueError: If config not found
        """
        old_config = db.query(AgentConfigVersion).filter(
            AgentConfigVersion.config_id == config_id
        ).first()
        if not old_config:
            raise ValueError(f"Config version {config_id} not found")

        agent_id = old_config.agent_id
        app_id = db.query(Agent).filter(Agent.agent_id == agent_id).first().app_id

        # Deactivate current active version
        db.query(AgentConfigVersion).filter(
            AgentConfigVersion.agent_id == agent_id,
            AgentConfigVersion.is_active.is_(True),
        ).update({AgentConfigVersion.is_active: False})

        # Get next version number
        max_version = (
            db.query(AgentConfigVersion.version_number)
            .filter(AgentConfigVersion.agent_id == agent_id)
            .order_by(desc(AgentConfigVersion.version_number))
            .first()
        )
        next_version = (max_version[0] + 1) if max_version else 1

        # Create new snapshot from old values
        new_snapshot = AgentConfigVersion(
            agent_id=agent_id,
            version_number=next_version,
            is_active=True,
            system_prompt=old_config.system_prompt,
            persona=old_config.persona,
            domain=old_config.domain,
            tone=old_config.tone,
            constraints=old_config.constraints or [],
            allowed_tools=old_config.allowed_tools or [],
            memory_scope=old_config.memory_scope,
            created_by_user_id=created_by_user_id,
        )
        db.add(new_snapshot)
        db.flush()

        # Log the restore action
        ConfigAuditService.log_change(
            db=db,
            agent_id=agent_id,
            app_id=app_id,
            config_id=new_snapshot.config_id,
            change_type=ChangeType.RESTORE,
            changed_by_user_id=created_by_user_id,
            change_reason=change_reason or f"Restored from version {old_config.version_number}",
            related_config_id=config_id,
        )

        return new_snapshot
    
    @staticmethod
    def compare_versions(
        db: Session,
        config_id_1: int,
        config_id_2: int,
    ) -> dict:
        """
        Compare two config versions and return differences.
        
        Args:
            db: Database session
            config_id_1: First config version ID
            config_id_2: Second config version ID
        
        Returns:
            Dict with keys: version_1, version_2, differences
            differences is a dict of field_name -> (old_value, new_value)
        
        Raises:
            ValueError: If either config not found
        """
        v1 = db.query(AgentConfigVersion).filter(
            AgentConfigVersion.config_id == config_id_1
        ).first()
        v2 = db.query(AgentConfigVersion).filter(
            AgentConfigVersion.config_id == config_id_2
        ).first()

        if not v1 or not v2:
            raise ValueError(
                f"Config versions not found: v1={config_id_1}, v2={config_id_2}"
            )

        # Compare all mutable fields
        differences = {}
        fields = [
            "system_prompt",
            "persona",
            "domain",
            "tone",
            "constraints",
            "allowed_tools",
            "memory_scope",
        ]

        for field in fields:
            val1 = getattr(v1, field)
            val2 = getattr(v2, field)
            if val1 != val2:
                differences[field] = {"from": val1, "to": val2}

        return {
            "version_1": {
                "config_id": v1.config_id,
                "version_number": v1.version_number,
                "is_active": v1.is_active,
                "created_at": v1.created_at,
            },
            "version_2": {
                "config_id": v2.config_id,
                "version_number": v2.version_number,
                "is_active": v2.is_active,
                "created_at": v2.created_at,
            },
            "differences": differences,
        }