"""
Audit Log: Immutable action logging for compliance.

This module provides an append-only audit log for tracking all
significant actions in the CMA generation process. The log is
critical for regulatory compliance and debugging.

All log entries are timestamped and include correlation IDs
for tracing actions across the system.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.context import get_run_id
from app.version import AppVersion

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    """Types of auditable actions."""
    
    # Intent parsing
    NOTES_RECEIVED = "notes_received"
    INTENT_PARSED = "intent_parsed"
    INTENT_VALIDATION_FAILED = "intent_validation_failed"
    
    # Query execution
    QUERY_PLANNED = "query_planned"
    QUERY_EXECUTED = "query_executed"
    QUERY_FAILED = "query_failed"
    
    # Data retrieval
    CANDIDATES_RETRIEVED = "candidates_retrieved"
    CANDIDATES_CAPPED = "candidates_capped"
    
    # Comp selection
    COMPS_SELECTED = "comps_selected"
    COMP_REJECTED = "comp_rejected"
    
    # Analytics
    ADJUSTMENTS_CALCULATED = "adjustments_calculated"
    OUTLIERS_DETECTED = "outliers_detected"
    VALUE_ESTIMATED = "value_estimated"
    
    # Report generation
    REPORT_GENERATED = "report_generated"
    REPORT_VERIFIED = "report_verified"
    HALLUCINATION_DETECTED = "hallucination_detected"
    REPORT_FAILED = "report_failed"
    
    # Data access
    FIELD_FILTERED = "field_filtered"
    TIER_RESTRICTION_APPLIED = "tier_restriction_applied"
    
    # Review & Verification
    REVIEW_STARTED = "review_started"
    REVIEW_COMPLETED = "review_completed"
    ASSUMPTIONS_MODIFIED = "assumptions_modified"

    # New Roadmap Actions
    PARSE = "parse"
    BUILD_QUERY = "build_query"
    FETCH_LISTINGS = "fetch_listings"
    RANK = "rank"
    SELECT = "select"
    CALCULATE = "calculate"
    GENERATE_NARRATIVE = "generate_narrative"
    VERIFY = "verify"
    RENDER = "render"


@dataclass
class AuditEntry:
    """A single audit log entry."""
    
    action: AuditAction
    timestamp: datetime
    correlation_id: str
    details: dict[str, Any] = field(default_factory=dict)
    user_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    app_versions: dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "action": self.action.value,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "details": self.details,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "app_versions": self.app_versions,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class AuditLog:
    """
    Append-only audit log for CMA operations.
    
    Supports multiple backends:
    - In-memory (for testing)
    - File-based (for production)
    - Future: Database, external logging service
    """
    
    def __init__(
        self,
        log_path: str | Path | None = None,
        session_id: str | None = None
    ):
        """
        Initialize audit log.
        
        Args:
            log_path: Path to log file (None for in-memory only)
            session_id: Session identifier for grouping entries
        """
        self.log_path = Path(log_path) if log_path else None
        self.session_id = session_id or str(uuid4())
        self._entries: list[AuditEntry] = []
        self._correlation_id: str | None = None
    
    def start_correlation(self, correlation_id: str | None = None) -> str:
        """
        Start a new correlation context.
        
        All subsequent log entries will be tagged with this ID
        until end_correlation() is called.
        
        Args:
            correlation_id: Optional explicit ID, or auto-generate
            
        Returns:
            The correlation ID
        """
        self._correlation_id = correlation_id or str(uuid4())
        return self._correlation_id
    
    def end_correlation(self):
        """End the current correlation context."""
        self._correlation_id = None
    
    def log(
        self,
        action: AuditAction,
        details: dict[str, Any] | None = None,
        user_id: str | None = None
    ) -> AuditEntry:
        """
        Log an action.
        
        Args:
            action: The action being logged
            details: Additional details about the action
            user_id: Optional user identifier
            
        Returns:
            The created AuditEntry
        """
        entry = AuditEntry(
            action=action,
            timestamp=datetime.utcnow(),
            correlation_id=self._correlation_id or str(uuid4()),
            details=details or {},
            user_id=user_id,
            session_id=self.session_id,
            run_id=get_run_id(),
            app_versions={v.name: v.value for v in AppVersion}
        )
        
        self._entries.append(entry)
        
        # Write to file if configured
        if self.log_path:
            self._write_to_file(entry)
        
        # Also log to standard logger
        logger.info(
            f"AUDIT: {action.value} | {entry.correlation_id} | {details}"
        )
        
        return entry
    
    def _write_to_file(self, entry: AuditEntry):
        """Append entry to log file."""
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a") as f:
                f.write(entry.to_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
    
    def get_entries(
        self,
        correlation_id: str | None = None,
        action: AuditAction | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None
    ) -> list[AuditEntry]:
        """
        Query audit entries.
        
        Args:
            correlation_id: Filter by correlation ID
            action: Filter by action type
            start_time: Filter by minimum timestamp
            end_time: Filter by maximum timestamp
            
        Returns:
            List of matching entries
        """
        results = self._entries.copy()
        
        if correlation_id:
            results = [e for e in results if e.correlation_id == correlation_id]
        
        if action:
            results = [e for e in results if e.action == action]
        
        if start_time:
            results = [e for e in results if e.timestamp >= start_time]
        
        if end_time:
            results = [e for e in results if e.timestamp <= end_time]
        
        return results
    
    def get_correlation_trace(self, correlation_id: str) -> list[AuditEntry]:
        """Get all entries for a correlation ID, sorted by time."""
        entries = self.get_entries(correlation_id=correlation_id)
        return sorted(entries, key=lambda e: e.timestamp)
    
    def export_json(self) -> str:
        """Export all entries as JSON array."""
        return json.dumps([e.to_dict() for e in self._entries], indent=2)
    
    def clear(self):
        """Clear in-memory entries (does not affect file log)."""
        self._entries = []


# Global audit log instance
_audit_log: AuditLog | None = None


def get_audit_log() -> AuditLog:
    """Get or create the global audit log instance."""
    global _audit_log
    if _audit_log is None:
        _audit_log = AuditLog()
    return _audit_log


def set_audit_log(log: AuditLog):
    """Set the global audit log instance."""
    global _audit_log
    _audit_log = log


def audit(
    action: AuditAction,
    details: dict[str, Any] | None = None,
    user_id: str | None = None
) -> AuditEntry:
    """
    Convenience function to log to the global audit log.
    
    Args:
        action: The action being logged
        details: Additional details
        user_id: Optional user identifier
        
    Returns:
        The created AuditEntry
    """
    return get_audit_log().log(action, details, user_id)
