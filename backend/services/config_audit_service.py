from sqlalchemy.orm import Session
from models.config_audit_log import ConfigAuditLog, ChangeType
from models.agent_config_version import AgentConfigVersion
import json
from datetime import datetime

class ConfigAuditService:
    """Manages audit logging for agent config changes."""

    @staticmethod
    def log_change(
        db: Session,
        agent_id: int,
        app_id: int,
        config_id: int,
        change_type: ChangeType,
        changed_by_user_id: int,
        field_name: str = None,
        old_value: any = None,
        new_value: any = None,
        change_reason: str = None,
        related_config_id: int = None,
    ) -> ConfigAuditLog:
        """
        Log a configuration change.
        
        Args:
            db: Database session
            agent_id: ID of the agent
            app_id: ID of the app
            config_id: ID of the config version that was changed
            change_type: Type of change (CREATE, UPDATE, RESTORE, etc.)
            changed_by_user_id: User ID who made the change
            field_name: Optional field name that was changed
            old_value: Optional old value (will be JSON serialized)
            new_value: Optional new value (will be JSON serialized)
            change_reason: Optional reason for the change
            related_config_id: Optional related config (e.g., for restore, the old config_id)
        
        Returns:
            ConfigAuditLog instance
        """
        audit_log = ConfigAuditLog(
            config_id=config_id,
            agent_id=agent_id,
            app_id=app_id,
            change_type=change_type,
            changed_by_user_id=changed_by_user_id,
            field_name=field_name,
            old_value=json.dumps(old_value) if old_value is not None else None,
            new_value=json.dumps(new_value) if new_value is not None else None,
            change_reason=change_reason,
            related_config_id=related_config_id,
            changed_at=datetime.utcnow(),
        )
        db.add(audit_log)
        return audit_log

    @staticmethod
    def get_audit_history(
        db: Session,
        config_id: int,
        limit: int = 100,
    ) -> list:
        """Get audit history for a specific config version (newest first)."""
        return db.query(ConfigAuditLog)\
            .filter(ConfigAuditLog.config_id == config_id)\
            .order_by(ConfigAuditLog.changed_at.desc())\
            .limit(limit)\
            .all()

    @staticmethod
    def get_agent_audit_history(
        db: Session,
        agent_id: int,
        app_id: int,
        limit: int = 200,
    ) -> list:
        """Get complete audit history for an agent (newest first)."""
        return db.query(ConfigAuditLog)\
            .filter(
                ConfigAuditLog.agent_id == agent_id,
                ConfigAuditLog.app_id == app_id,
            )\
            .order_by(ConfigAuditLog.changed_at.desc())\
            .limit(limit)\
            .all()

    @staticmethod
    def get_field_change_history(
        db: Session,
        agent_id: int,
        field_name: str,
        limit: int = 100,
    ) -> list:
        """Get history of changes to a specific field across all config versions."""
        return db.query(ConfigAuditLog)\
            .filter(
                ConfigAuditLog.agent_id == agent_id,
                ConfigAuditLog.field_name == field_name,
            )\
            .order_by(ConfigAuditLog.changed_at.desc())\
            .limit(limit)\
            .all()