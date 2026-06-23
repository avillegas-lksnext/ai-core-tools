"""Response schemas for audit analytics endpoints."""

from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class TimelineEntry(BaseModel):
    """Single entry in config change timeline."""
    timestamp: str  # ISO format datetime
    change_type: str
    field_name: Optional[str] = None
    changed_by_user_id: Optional[int] = None
    change_reason: Optional[str] = None
    summary: str

    model_config = ConfigDict(from_attributes=True)


class ChangeTimeline(BaseModel):
    """Complete timeline of config changes for an agent."""
    agent_id: int
    total_changes: int
    date_range: Dict[str, Optional[str]]  # {"start": str, "end": str}
    timeline: List[TimelineEntry]
    
    model_config = ConfigDict(from_attributes=True)


class RiskyChange(BaseModel):
    """Represents a risky configuration change."""
    audit_id: int
    timestamp: str  # ISO format datetime
    change_type: str
    changed_by_user_id: Optional[int] = None
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    reason: str

    model_config = ConfigDict(from_attributes=True)


class RiskAnalysisResponse(BaseModel):
    """Risk analysis report for agent config changes."""
    agent_id: int
    analysis_period_days: int
    risk_score: float  # 0-100
    risky_changes: List[RiskyChange]
    summary: str
    
    model_config = ConfigDict(from_attributes=True)


class AuditFilterResponse(BaseModel):
    """Paginated filtered audit logs."""
    agent_id: int
    total_count: int
    limit: int
    offset: int
    logs: List[Dict[str, Any]]  # List of ConfigAuditLogRead dicts

    model_config = ConfigDict(from_attributes=True)


class ChangeFrequencySummary(BaseModel):
    """Summary of change frequency by date, type, user."""
    agent_id: int
    period_days: int
    total_changes: int
    by_date: Dict[str, int]  # {"2026-01-15": 3, ...}
    by_change_type: Dict[str, int]  # {"CREATE": 1, "UPDATE": 5, ...}
    by_user: Dict[str, int]  # {"user_id": count, ...}
    average_changes_per_day: float
    
    model_config = ConfigDict(from_attributes=True)