"""
Provenance: Value source tracking for report data.

This module tracks the origin of every value in a CMA report.
Each numeric value, date, or significant data point has a
provenance record that traces back to:
1. Raw source data (listing ID, field name)
2. Any computation applied (formula, aggregation)
3. Timestamp of retrieval

This is CRITICAL for:
- Regulatory compliance audits
- Disputing hallucination claims
- Debugging value discrepancies
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from typing import Any
from uuid import uuid4

from app.context import get_run_id


class ProvenanceType(str, Enum):
    """Types of provenance records."""
    
    # Direct from data source
    RAW_VALUE = "raw_value"
    
    # Computed from other values
    COMPUTED = "computed"
    
    # Aggregation (mean, median, etc.)
    AGGREGATED = "aggregated"
    
    # User-provided input
    USER_INPUT = "user_input"
    
    # System default
    DEFAULT = "default"


@dataclass
class ProvenanceRecord:
    """
    Provenance record for a single value.
    
    Every significant value in ReportJSON should have a corresponding
    provenance record that traces its origin.
    """
    
    # The value being tracked
    value: Decimal | int | float | str | datetime
    
    # Unique identifier for this provenance record
    provenance_id: str = field(default_factory=lambda: str(uuid4()))
    
    # Type of provenance
    provenance_type: ProvenanceType = ProvenanceType.RAW_VALUE
    
    # Source information (for RAW_VALUE)
    source_record_id: str | None = None  # e.g., ListingId
    source_field: str | None = None  # e.g., "ClosePrice"
    source_backend: str | None = None  # e.g., "csv", "reso_mock"
    
    # Computation information (for COMPUTED/AGGREGATED)
    computation: str | None = None  # e.g., "ClosePrice / LivingArea"
    input_provenance_ids: list[str] = field(default_factory=list)
    aggregation_method: str | None = None  # e.g., "median", "mean"
    aggregation_count: int | None = None
    
    # Metadata
    retrieved_at: datetime = field(default_factory=datetime.utcnow)
    description: str | None = None
    run_id: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        value_repr = self.value
        if isinstance(self.value, Decimal):
            value_repr = float(self.value)
        elif isinstance(self.value, datetime):
            value_repr = self.value.isoformat()
        
        return {
            "provenance_id": self.provenance_id,
            "value": value_repr,
            "provenance_type": self.provenance_type.value,
            "source_record_id": self.source_record_id,
            "source_field": self.source_field,
            "source_backend": self.source_backend,
            "computation": self.computation,
            "input_provenance_ids": self.input_provenance_ids,
            "aggregation_method": self.aggregation_method,
            "aggregation_count": self.aggregation_count,
            "retrieved_at": self.retrieved_at.isoformat(),
            "description": self.description,
            "run_id": self.run_id
        }


class ProvenanceTracker:
    """
    Tracks provenance for all values in a CMA report.
    
    Usage:
        tracker = ProvenanceTracker()
        
        # Track a raw value from data source
        prov = tracker.track_raw_value(
            value=Decimal("500000"),
            record_id="ABC123",
            field="ClosePrice",
            backend="csv"
        )
        
        # Track a computed value
        ppsf_prov = tracker.track_computed(
            value=Decimal("275.50"),
            computation="ClosePrice / LivingArea",
            inputs=[price_prov.provenance_id, sqft_prov.provenance_id]
        )
    """
    
    def __init__(self):
        self._records: dict[str, ProvenanceRecord] = {}
        self._by_value: dict[str, list[str]] = {}  # value -> provenance_ids
    
    def track_raw_value(
        self,
        value: Decimal | int | float | str | datetime,
        record_id: str,
        field: str,
        backend: str,
        description: str | None = None
    ) -> ProvenanceRecord:
        """
        Track a value directly from a data source.
        
        Args:
            value: The value being tracked
            record_id: Source record identifier (e.g., ListingId)
            field: Source field name
            backend: Data source name
            description: Optional description
            
        Returns:
            ProvenanceRecord for the value
        """
        record = ProvenanceRecord(
            value=value,
            provenance_type=ProvenanceType.RAW_VALUE,
            source_record_id=record_id,
            source_field=field,
            source_backend=backend,
            source_backend=backend,
            description=description,
            run_id=get_run_id()
        )
        
        self._store(record)
        return record
    
    def track_computed(
        self,
        value: Decimal | int | float,
        computation: str,
        inputs: list[str],
        description: str | None = None
    ) -> ProvenanceRecord:
        """
        Track a computed value.
        
        Args:
            value: The computed value
            computation: Description of the computation
            inputs: List of provenance IDs for input values
            description: Optional description
            
        Returns:
            ProvenanceRecord for the value
        """
        record = ProvenanceRecord(
            value=value,
            provenance_type=ProvenanceType.COMPUTED,
            computation=computation,
            input_provenance_ids=inputs,
            input_provenance_ids=inputs,
            description=description,
            run_id=get_run_id()
        )
        
        self._store(record)
        return record
    
    def track_aggregated(
        self,
        value: Decimal | int | float,
        method: str,
        inputs: list[str],
        count: int,
        description: str | None = None
    ) -> ProvenanceRecord:
        """
        Track an aggregated value.
        
        Args:
            value: The aggregated value
            method: Aggregation method (mean, median, etc.)
            inputs: List of provenance IDs for input values
            count: Number of values aggregated
            description: Optional description
            
        Returns:
            ProvenanceRecord for the value
        """
        record = ProvenanceRecord(
            value=value,
            provenance_type=ProvenanceType.AGGREGATED,
            aggregation_method=method,
            input_provenance_ids=inputs,
            aggregation_count=count,
            aggregation_count=count,
            description=description,
            run_id=get_run_id()
        )
        
        self._store(record)
        return record
    
    def track_user_input(
        self,
        value: Decimal | int | float | str,
        description: str | None = None
    ) -> ProvenanceRecord:
        """
        Track a user-provided value.
        
        Args:
            value: User-provided value
            description: Description of the input
            
        Returns:
            ProvenanceRecord for the value
        """
        record = ProvenanceRecord(
            value=value,
            provenance_type=ProvenanceType.USER_INPUT,
            provenance_type=ProvenanceType.USER_INPUT,
            description=description,
            run_id=get_run_id()
        )
        
        self._store(record)
        return record
    
    def _store(self, record: ProvenanceRecord):
        """Store a provenance record."""
        self._records[record.provenance_id] = record
        
        # Index by value for lookup
        value_key = str(record.value)
        if value_key not in self._by_value:
            self._by_value[value_key] = []
        self._by_value[value_key].append(record.provenance_id)
    
    def get(self, provenance_id: str) -> ProvenanceRecord | None:
        """Get a provenance record by ID."""
        return self._records.get(provenance_id)
    
    def find_by_value(
        self,
        value: Decimal | int | float | str
    ) -> list[ProvenanceRecord]:
        """Find all provenance records for a value."""
        value_key = str(value)
        ids = self._by_value.get(value_key, [])
        return [self._records[pid] for pid in ids]
    
    def get_lineage(self, provenance_id: str) -> list[ProvenanceRecord]:
        """
        Get the full lineage of a value.
        
        Traces back through all inputs to find ultimate sources.
        
        Args:
            provenance_id: ID of the provenance record
            
        Returns:
            List of all provenance records in the lineage
        """
        if provenance_id not in self._records:
            return []
        
        visited = set()
        lineage = []
        
        def trace(pid: str):
            if pid in visited:
                return
            visited.add(pid)
            
            record = self._records.get(pid)
            if record:
                lineage.append(record)
                for input_pid in record.input_provenance_ids:
                    trace(input_pid)
        
        trace(provenance_id)
        return lineage
    
    def export_all(self) -> list[dict[str, Any]]:
        """Export all provenance records."""
        return [r.to_dict() for r in self._records.values()]
    
    def get_all_values(self) -> set[Decimal]:
        """
        Get all tracked numeric values.
        
        Useful for building the allowed_values set for hallucination checking.
        """
        values = set()
        for record in self._records.values():
            if isinstance(record.value, (Decimal, int, float)):
                values.add(Decimal(str(record.value)))
        return values
