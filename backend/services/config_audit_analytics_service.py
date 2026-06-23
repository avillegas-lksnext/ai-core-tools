"""Advanced audit analytics and filtering for agent configuration changes."""

from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_
import csv
import io
import json

from models.config_audit_log import ConfigAuditLog, ChangeType
from models.agent_config_version import AgentConfigVersion
from models.user import User


class ConfigAuditAnalyticsService:
    """Advanced filtering, analytics, and reporting for audit logs."""

    @staticmethod
    def filter_audit_logs(
        db: Session,
        agent_id: int,
        app_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        change_types: Optional[List[str]] = None,
        changed_by_user_id: Optional[int] = None,
        field_name: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[List[ConfigAuditLog], int]:
        """
        Advanced filtering of audit logs with multiple criteria.
        
        Args:
            db: Database session
            agent_id: Agent ID
            app_id: App ID
            start_date: Filter from this date onwards (inclusive)
            end_date: Filter up to this date (inclusive)
            change_types: List of ChangeType enum values to filter
            changed_by_user_id: Filter by specific user who made changes
            field_name: Filter by specific field that was changed
            limit: Results per page (max 500)
            offset: Pagination offset
            
        Returns:
            Tuple of (filtered_logs, total_count)
        """
        query = db.query(ConfigAuditLog).filter(
            ConfigAuditLog.agent_id == agent_id,
            ConfigAuditLog.app_id == app_id,
        )

        if start_date:
            query = query.filter(ConfigAuditLog.changed_at >= start_date)

        if end_date:
            # Include entire end_date day
            query = query.filter(ConfigAuditLog.changed_at < end_date + timedelta(days=1))

        if change_types:
            query = query.filter(ConfigAuditLog.change_type.in_(change_types))

        if changed_by_user_id:
            query = query.filter(ConfigAuditLog.changed_by_user_id == changed_by_user_id)

        if field_name:
            query = query.filter(ConfigAuditLog.field_name == field_name)

        total_count = query.count()
        logs = query.order_by(ConfigAuditLog.changed_at.desc()).limit(limit).offset(offset).all()

        return logs, total_count

    @staticmethod
    def get_change_timeline(
        db: Session,
        agent_id: int,
        app_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        Get chronological timeline of all agent config changes.
        
        Returns:
            {
                "agent_id": int,
                "total_changes": int,
                "date_range": {"start": datetime, "end": datetime},
                "timeline": [
                    {
                        "timestamp": datetime,
                        "change_type": str,
                        "field_name": str,
                        "changed_by_user_id": int,
                        "change_reason": str,
                        "summary": str  # Human-readable summary
                    }
                ]
            }
        """
        logs, total = ConfigAuditAnalyticsService.filter_audit_logs(
            db, agent_id, app_id, start_date, end_date, limit=1000
        )

        timeline_entries = []
        for log in reversed(logs):  # Oldest first
            summary = ConfigAuditAnalyticsService._summarize_change(log)
            timeline_entries.append({
                "timestamp": log.changed_at.isoformat(),
                "change_type": log.change_type.value,
                "field_name": log.field_name,
                "changed_by_user_id": log.changed_by_user_id,
                "change_reason": log.change_reason,
                "summary": summary,
            })

        return {
            "agent_id": agent_id,
            "total_changes": len(logs),
            "date_range": {
                "start": logs[-1].changed_at.isoformat() if logs else None,
                "end": logs[0].changed_at.isoformat() if logs else None,
            },
            "timeline": timeline_entries,
        }

    @staticmethod
    def get_risk_analysis(
        db: Session,
        agent_id: int,
        app_id: int,
        days: int = 30,
    ) -> dict:
        """
        Risk analysis: identify potentially risky configuration changes.
        
        Risk factors:
        - PROMPT_UPDATE by non-admin
        - SKILL_CHANGE by viewer-level user
        - TOOL_CHANGE by editor
        - Frequency: >5 changes/day
        
        Returns:
            {
                "agent_id": int,
                "analysis_period_days": int,
                "risk_score": float (0-100),
                "risky_changes": [
                    {
                        "audit_id": int,
                        "timestamp": datetime,
                        "change_type": str,
                        "changed_by_user_id": int,
                        "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
                        "reason": str
                    }
                ],
                "summary": str
            }
        """
        start_date = datetime.utcnow() - timedelta(days=days)
        logs, _ = ConfigAuditAnalyticsService.filter_audit_logs(
            db, agent_id, app_id, start_date=start_date, limit=1000
        )

        risky_changes = []
        change_count_by_day = {}

        for log in logs:
            day_key = log.changed_at.date().isoformat()
            change_count_by_day[day_key] = change_count_by_day.get(day_key, 0) + 1

            risk_level, reason = ConfigAuditAnalyticsService._assess_risk(db, log)
            if risk_level != "LOW":
                risky_changes.append({
                    "audit_id": log.audit_id,
                    "timestamp": log.changed_at.isoformat(),
                    "change_type": log.change_type.value,
                    "changed_by_user_id": log.changed_by_user_id,
                    "risk_level": risk_level,
                    "reason": reason,
                })

        # Calculate risk score
        risk_score = 0.0
        if risky_changes:
            risk_score = min(100.0, len(risky_changes) * 5.0)

        # Check for frequency anomaly
        for day, count in change_count_by_day.items():
            if count > 5:
                risk_score = min(100.0, risk_score + 10.0)

        summary = f"Found {len(risky_changes)} risky changes in the last {days} days."
        if risk_score > 50:
            summary += " Recommend reviewing recent changes."

        return {
            "agent_id": agent_id,
            "analysis_period_days": days,
            "risk_score": risk_score,
            "risky_changes": risky_changes,
            "summary": summary,
        }

    @staticmethod
    def export_audit_to_csv(
        db: Session,
        agent_id: int,
        app_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> str:
        """
        Export audit log to CSV format.
        
        Returns:
            CSV string with headers and rows
        """
        logs, _ = ConfigAuditAnalyticsService.filter_audit_logs(
            db, agent_id, app_id, start_date, end_date, limit=10000
        )

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "audit_id",
                "timestamp",
                "change_type",
                "field_name",
                "changed_by_user_id",
                "change_reason",
                "old_value",
                "new_value",
                "config_id",
            ],
        )

        writer.writeheader()
        for log in reversed(logs):  # Oldest first
            writer.writerow({
                "audit_id": log.audit_id,
                "timestamp": log.changed_at.isoformat(),
                "change_type": log.change_type.value,
                "field_name": log.field_name or "",
                "changed_by_user_id": log.changed_by_user_id or "",
                "change_reason": log.change_reason or "",
                "old_value": log.old_value or "",
                "new_value": log.new_value or "",
                "config_id": log.config_id,
            })

        return output.getvalue()

    @staticmethod
    def get_change_frequency_summary(
        db: Session,
        agent_id: int,
        app_id: int,
        days: int = 30,
    ) -> dict:
        """
        Get summary of change frequency grouped by day and change type.
        
        Returns:
            {
                "agent_id": int,
                "period_days": int,
                "total_changes": int,
                "by_date": {"2026-01-15": 3, ...},
                "by_change_type": {"CREATE": 1, "UPDATE": 5, ...},
                "by_user": {"user_id_1": 3, "user_id_2": 5, ...},
                "average_changes_per_day": float
            }
        """
        start_date = datetime.utcnow() - timedelta(days=days)
        logs, _ = ConfigAuditAnalyticsService.filter_audit_logs(
            db, agent_id, app_id, start_date=start_date, limit=1000
        )

        by_date = {}
        by_change_type = {}
        by_user = {}

        for log in logs:
            day_key = log.changed_at.date().isoformat()
            by_date[day_key] = by_date.get(day_key, 0) + 1

            change_type = log.change_type.value
            by_change_type[change_type] = by_change_type.get(change_type, 0) + 1

            user_id = log.changed_by_user_id or "unknown"
            by_user[str(user_id)] = by_user.get(str(user_id), 0) + 1

        avg_per_day = len(logs) / max(days, 1)

        return {
            "agent_id": agent_id,
            "period_days": days,
            "total_changes": len(logs),
            "by_date": by_date,
            "by_change_type": by_change_type,
            "by_user": by_user,
            "average_changes_per_day": round(avg_per_day, 2),
        }

    # ========== Helper Methods ==========

    @staticmethod
    def _summarize_change(log: ConfigAuditLog) -> str:
        """Generate human-readable summary of a change."""
        change_type = log.change_type.value
        field = log.field_name or "config"

        if change_type == "CREATE":
            return "Initial configuration created"
        elif change_type == "RESTORE":
            return "Configuration restored from previous version"
        elif change_type == "PROMPT_UPDATE":
            return "System prompt updated"
        elif change_type == "SKILL_CHANGE":
            return "Skills modified"
        elif change_type == "TOOL_CHANGE":
            return "Allowed tools changed"
        elif change_type == "MCP_CHANGE":
            return "MCP configuration updated"
        else:
            return f"{change_type}: {field} changed"

    @staticmethod
    def _assess_risk(db: Session, log: ConfigAuditLog) -> tuple[str, str]:
        """
        Assess risk level of a change.
        
        Returns:
            (risk_level: str, reason: str)
        """
        change_type = log.change_type.value

        # Critical: system_prompt changed
        if change_type == "PROMPT_UPDATE":
            return "HIGH", "System prompt modification - critical component"

        # High: skill or tool changes
        if change_type in ["SKILL_CHANGE", "TOOL_CHANGE"]:
            return "MEDIUM", f"{change_type.lower()} - affects agent capabilities"

        # Medium: MCP changes
        if change_type == "MCP_CHANGE":
            return "MEDIUM", "MCP configuration modified - affects external integrations"

        # Low: restore, create
        return "LOW", "Routine configuration operation"