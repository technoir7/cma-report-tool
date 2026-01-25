"""
QueryPlan: Constrained, bounded query representation.

This module defines the query plan that is generated from IntentIR and
used by connectors to fetch data. All queries are bounded and capped
to prevent unbounded data access.

CRITICAL: Query execution is DETERMINISTIC and CODE-CONTROLLED.
LLMs are NEVER involved in query construction or execution.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class FilterOperator(str, Enum):
    """Supported filter operators for queries."""
    EQ = "eq"      # equals
    NE = "ne"      # not equals
    GT = "gt"      # greater than
    GE = "ge"      # greater than or equal
    LT = "lt"      # less than
    LE = "le"      # less than or equal
    CONTAINS = "contains"
    STARTSWITH = "startswith"


class SortDirection(str, Enum):
    """Sort direction for query results."""
    ASC = "asc"
    DESC = "desc"


class FilterCondition(BaseModel):
    """A single filter condition for a query."""
    
    field: str = Field(..., description="Field name to filter on")
    operator: FilterOperator = Field(..., description="Filter operator")
    value: str | int | float | bool | date = Field(..., description="Filter value")
    
    def to_odata(self) -> str:
        """Convert to OData $filter expression."""
        value_str = self._format_value()
        
        if self.operator == FilterOperator.CONTAINS:
            return f"contains({self.field}, {value_str})"
        elif self.operator == FilterOperator.STARTSWITH:
            return f"startswith({self.field}, {value_str})"
        else:
            return f"{self.field} {self.operator.value} {value_str}"
    
    def _format_value(self) -> str:
        """Format value for OData query."""
        if isinstance(self.value, str):
            # Escape single quotes in strings
            escaped = self.value.replace("'", "''")
            return f"'{escaped}'"
        elif isinstance(self.value, bool):
            return "true" if self.value else "false"
        elif isinstance(self.value, date):
            return self.value.isoformat()
        else:
            return str(self.value)


class SortCriterion(BaseModel):
    """A single sort criterion for query ordering."""
    
    field: str = Field(..., description="Field name to sort by")
    direction: SortDirection = Field(default=SortDirection.DESC)
    
    def to_odata(self) -> str:
        """Convert to OData $orderby expression."""
        return f"{self.field} {self.direction.value}"


class QueryPlan(BaseModel):
    """
    A bounded, constrained query plan for fetching comparable properties.
    
    HARD CAPS (enforced at validation):
    - max_results: Maximum 200 candidates
    - selected_count: Maximum 20 selected comps
    """
    
    # Fields to select (whitelist approach)
    select_fields: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Fields to retrieve (max 50)"
    )
    
    # Filter conditions
    filters: list[FilterCondition] = Field(
        default_factory=list,
        max_length=20,
        description="Filter conditions (max 20)"
    )
    
    # Sort order
    order_by: list[SortCriterion] = Field(
        default_factory=list,
        max_length=3,
        description="Sort criteria (max 3)"
    )
    
    # Result limits (HARD CAPS)
    max_results: int = Field(
        default=200,
        ge=1,
        le=200,
        description="Maximum results to return (HARD CAP: 200)"
    )
    
    # Geographic bounds
    center_lat: float | None = Field(default=None, ge=-90, le=90)
    center_lon: float | None = Field(default=None, ge=-180, le=180)
    radius_miles: float | None = Field(default=None, ge=0.1, le=5.0)
    
    # Date range for sales
    sale_date_min: date | None = Field(default=None)
    sale_date_max: date | None = Field(default=None)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    intent_hash: str | None = Field(
        default=None,
        description="Hash of source IntentIR for traceability"
    )
    
    @field_validator("max_results")
    @classmethod
    def enforce_max_results_cap(cls, v: int) -> int:
        """Enforce hard cap on max results."""
        if v > 200:
            raise ValueError("max_results cannot exceed 200 (hard cap)")
        return v
    
    def to_odata_params(self) -> dict[str, str]:
        """
        Convert query plan to OData query parameters.
        
        Returns dict suitable for httpx params.
        """
        params = {}
        
        # $select
        if self.select_fields:
            params["$select"] = ",".join(self.select_fields)
        
        # $filter
        if self.filters:
            filter_clauses = [f.to_odata() for f in self.filters]
            params["$filter"] = " and ".join(filter_clauses)
        
        # $orderby
        if self.order_by:
            orderby_clauses = [s.to_odata() for s in self.order_by]
            params["$orderby"] = ",".join(orderby_clauses)
        
        # $top (enforce hard cap)
        params["$top"] = str(min(self.max_results, 200))
        
        return params
    
    def add_filter(
        self,
        field: str,
        operator: FilterOperator,
        value: str | int | float | bool | date
    ) -> "QueryPlan":
        """Add a filter condition (returns new QueryPlan)."""
        if len(self.filters) >= 20:
            raise ValueError("Maximum 20 filter conditions allowed")
        
        new_filter = FilterCondition(field=field, operator=operator, value=value)
        return self.model_copy(
            update={"filters": self.filters + [new_filter]}
        )


class QueryPlanBuilder:
    """
    Builder for constructing QueryPlan from IntentIR.
    
    This is the ONLY place where IntentIR is translated to queries.
    The translation is deterministic and code-controlled.
    """
    
    # Default fields to select (Tier 0 safe fields)
    DEFAULT_SELECT_FIELDS = [
        "ListingId",
        "ListPrice",
        "ClosePrice",
        "CloseDate",
        "DaysOnMarket",
        "PropertyType",
        "BedroomsTotal",
        "BathroomsTotalInteger",
        "LivingArea",
        "LotSizeSquareFeet",
        "YearBuilt",
        "City",
        "StateOrProvince",
        "PostalCode",
        "Latitude",
        "Longitude",
        "StandardStatus",
    ]
    
    @classmethod
    def from_intent(
        cls,
        intent: "IntentIR",
        include_public_remarks: bool = False
    ) -> QueryPlan:
        """
        Build a QueryPlan from IntentIR.
        
        Args:
            intent: The parsed intent
            include_public_remarks: Whether to include Tier 1 fields
            
        Returns:
            A bounded, constrained QueryPlan
        """
        from domain.intent_ir import IntentIR
        import hashlib
        import json
        
        # Calculate intent hash for traceability
        intent_json = intent.model_dump_json(exclude_none=True)
        intent_hash = hashlib.sha256(intent_json.encode()).hexdigest()[:16]
        
        # Build select fields
        select_fields = cls.DEFAULT_SELECT_FIELDS.copy()
        if include_public_remarks:
            select_fields.append("PublicRemarks")
        
        # Build filters
        filters = []
        
        # City filter (only if specified)
        if intent.subject_city:
            filters.append(FilterCondition(
                field="City",
                operator=FilterOperator.EQ,
                value=intent.subject_city
            ))
        
        # State filter (only if specified)
        if intent.subject_state:
            filters.append(FilterCondition(
                field="StateOrProvince",
                operator=FilterOperator.EQ,
                value=intent.subject_state
            ))
        
        # Status filter (closed sales only)
        filters.append(FilterCondition(
            field="StandardStatus",
            operator=FilterOperator.EQ,
            value="Closed"
        ))
        
        # Property type filter
        if intent.property_type:
            property_type_map = {
                "SFR": "Residential",
                "Condo": "Condominium",
                "Townhouse": "Townhouse",
                "Multi": "Multi-Family"
            }
            filters.append(FilterCondition(
                field="PropertyType",
                operator=FilterOperator.EQ,
                value=property_type_map.get(intent.property_type, intent.property_type)
            ))
        
        # Bedroom filters
        if intent.subject_beds is not None:
            filters.append(FilterCondition(
                field="BedroomsTotal",
                operator=FilterOperator.GE,
                value=max(0, intent.subject_beds - 1)
            ))
            filters.append(FilterCondition(
                field="BedroomsTotal",
                operator=FilterOperator.LE,
                value=intent.subject_beds + 1
            ))
        
        # Square footage filters
        sqft_min, sqft_max = intent.get_sqft_range()
        if sqft_min is not None:
            filters.append(FilterCondition(
                field="LivingArea",
                operator=FilterOperator.GE,
                value=sqft_min
            ))
        if sqft_max is not None:
            filters.append(FilterCondition(
                field="LivingArea",
                operator=FilterOperator.LE,
                value=sqft_max
            ))
        
        # Price filters
        if intent.price_range_min is not None:
            filters.append(FilterCondition(
                field="ClosePrice",
                operator=FilterOperator.GE,
                value=intent.price_range_min
            ))
        if intent.price_range_max is not None:
            filters.append(FilterCondition(
                field="ClosePrice",
                operator=FilterOperator.LE,
                value=intent.price_range_max
            ))
        
        # Date filter for max age
        if intent.max_age_years > 0:
            from datetime import timedelta
            min_date = date.today() - timedelta(days=intent.max_age_years * 365)
            filters.append(FilterCondition(
                field="CloseDate",
                operator=FilterOperator.GE,
                value=min_date
            ))
        
        # Default sort: by close date descending
        order_by = [
            SortCriterion(field="CloseDate", direction=SortDirection.DESC)
        ]
        
        return QueryPlan(
            select_fields=select_fields,
            filters=filters,
            order_by=order_by,
            max_results=200,  # Hard cap
            radius_miles=intent.search_radius_miles,
            intent_hash=intent_hash
        )
