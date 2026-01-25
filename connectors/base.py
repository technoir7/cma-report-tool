"""
Base connector interface for MLS data sources.

All connectors must implement this interface to ensure consistent
behavior across different backends (RESO API, CSV, etc.).

CRITICAL: Connectors are the ONLY code that accesses MLS data.
All queries must be bounded and validated before execution.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from domain.policies import (
    BackendCapability,
    FieldTier,
    filter_fields_for_tier,
    validate_query_bounds,
    PolicyViolationError,
)
from domain.query_plan import QueryPlan


@dataclass
class ListingRecord:
    """
    A single listing record from the data source.
    
    Field names follow RESO Data Dictionary conventions.
    """
    raw_data: dict[str, Any]
    source: str
    retrieved_at: datetime
    
    def get(self, field: str, default: Any = None) -> Any:
        """Get a field value from the raw data."""
        return self.raw_data.get(field, default)
    
    def filter_to_tier(self, max_tier: FieldTier) -> dict[str, Any]:
        """Return data filtered to the specified tier."""
        return filter_fields_for_tier(self.raw_data, max_tier)


@dataclass
class SearchResult:
    """Result of a search query."""
    
    records: list[ListingRecord]
    total_count: int
    query_plan: QueryPlan
    executed_at: datetime
    backend: str
    
    # Degradation info
    was_capped: bool = False
    cap_applied: int | None = None
    unsupported_filters: list[str] | None = None


class DataConnector(ABC):
    """
    Abstract base class for MLS data connectors.
    
    All implementations must:
    1. Validate query bounds before execution
    2. Apply field tier filtering to results
    3. Enforce hard caps on result count
    4. Log all query executions
    """
    
    def __init__(self, source_name: str):
        self.source_name = source_name
        self._query_count = 0
        self._last_query_at: datetime | None = None
    
    @property
    @abstractmethod
    def capability(self) -> BackendCapability:
        """Return the capabilities of this backend."""
        ...
    
    @abstractmethod
    def _execute_search(self, query_plan: QueryPlan) -> list[dict[str, Any]]:
        """
        Execute the search query against the backend.
        
        This is the internal implementation that subclasses must provide.
        The public search() method handles validation and filtering.
        
        Args:
            query_plan: The validated query plan
            
        Returns:
            List of raw listing dictionaries
        """
        ...
    
    @abstractmethod
    def get_by_id(self, listing_id: str) -> ListingRecord | None:
        """
        Retrieve a single listing by ID.
        
        Args:
            listing_id: The listing identifier
            
        Returns:
            The listing record or None if not found
        """
        ...
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check if the backend is available."""
        ...
    
    def search(
        self,
        query_plan: QueryPlan,
        max_tier: FieldTier = FieldTier.SAFE
    ) -> SearchResult:
        """
        Execute a search with validation and filtering.
        
        This is the public entry point that ensures:
        1. Query bounds are valid
        2. Results are capped
        3. Field tiers are enforced
        
        Args:
            query_plan: The query to execute
            max_tier: Maximum field tier to include in results
            
        Returns:
            SearchResult with filtered records
            
        Raises:
            PolicyViolationError: If query bounds are invalid
        """
        # Validate query bounds
        violations = validate_query_bounds(
            max_results=query_plan.max_results,
            radius_miles=query_plan.radius_miles,
            filter_count=len(query_plan.filters),
            select_count=len(query_plan.select_fields)
        )
        
        if violations:
            raise PolicyViolationError(violations)
        
        # Track query execution
        self._query_count += 1
        self._last_query_at = datetime.utcnow()
        
        # Execute the search
        raw_results = self._execute_search(query_plan)
        
        # Apply hard cap
        was_capped = len(raw_results) > query_plan.max_results
        if was_capped:
            raw_results = raw_results[:query_plan.max_results]
        
        # Convert to ListingRecords with tier filtering
        records = []
        for raw in raw_results:
            filtered_data = filter_fields_for_tier(raw, max_tier)
            records.append(ListingRecord(
                raw_data=filtered_data,
                source=self.source_name,
                retrieved_at=self._last_query_at
            ))
        
        return SearchResult(
            records=records,
            total_count=len(records),
            query_plan=query_plan,
            executed_at=self._last_query_at,
            backend=self.source_name,
            was_capped=was_capped,
            cap_applied=query_plan.max_results if was_capped else None
        )
    
    def get_query_stats(self) -> dict[str, Any]:
        """Return statistics about queries executed."""
        return {
            "source": self.source_name,
            "query_count": self._query_count,
            "last_query_at": self._last_query_at.isoformat() if self._last_query_at else None,
        }
