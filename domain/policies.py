"""
Policies: Field tiers, capability matrix, and compliance enforcement.

This module defines the access control policies for MLS data.
These policies are ABSOLUTE and cannot be overridden at runtime.

CRITICAL COMPLIANCE RULES:
1. Tier 2+ fields are NEVER sent to LLM
2. All queries are bounded and capped
3. All data access is logged
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class FieldTier(int, Enum):
    """
    Data field access tiers.
    
    Tier 0: Safe - Can be freely used in LLM context
    Tier 1: Public Remarks - May contain PII, use with caution
    Tier 2: Restricted - Agent/broker info, NEVER to LLM
    Tier 3: Confidential - Owner/tax info, NEVER exposed
    """
    SAFE = 0
    PUBLIC_REMARKS = 1
    RESTRICTED = 2
    CONFIDENTIAL = 3


# Comprehensive field tier assignments following RESO Data Dictionary
FIELD_TIER_MAP: dict[str, FieldTier] = {
    # === TIER 0: SAFE FIELDS ===
    # These can be sent to LLM for narrative generation
    
    # Identifiers
    "ListingId": FieldTier.SAFE,
    "ListingKey": FieldTier.SAFE,
    
    # Pricing
    "ListPrice": FieldTier.SAFE,
    "ClosePrice": FieldTier.SAFE,
    "OriginalListPrice": FieldTier.SAFE,
    "PreviousListPrice": FieldTier.SAFE,
    
    # Dates
    "ListingContractDate": FieldTier.SAFE,
    "CloseDate": FieldTier.SAFE,
    "OnMarketDate": FieldTier.SAFE,
    "OffMarketDate": FieldTier.SAFE,
    "DaysOnMarket": FieldTier.SAFE,
    "CumulativeDaysOnMarket": FieldTier.SAFE,
    
    # Property Type
    "PropertyType": FieldTier.SAFE,
    "PropertySubType": FieldTier.SAFE,
    
    # Physical Characteristics
    "BedroomsTotal": FieldTier.SAFE,
    "BathroomsTotalInteger": FieldTier.SAFE,
    "BathroomsFull": FieldTier.SAFE,
    "BathroomsHalf": FieldTier.SAFE,
    "BathroomsThreeQuarter": FieldTier.SAFE,
    "LivingArea": FieldTier.SAFE,
    "LivingAreaUnits": FieldTier.SAFE,
    "LotSizeSquareFeet": FieldTier.SAFE,
    "LotSizeAcres": FieldTier.SAFE,
    "LotSizeArea": FieldTier.SAFE,
    "LotSizeUnits": FieldTier.SAFE,
    "YearBuilt": FieldTier.SAFE,
    "StoriesTotal": FieldTier.SAFE,
    "Levels": FieldTier.SAFE,
    
    # Garage/Parking
    "GarageSpaces": FieldTier.SAFE,
    "GarageYN": FieldTier.SAFE,
    "AttachedGarageYN": FieldTier.SAFE,
    "CarportSpaces": FieldTier.SAFE,
    "ParkingTotal": FieldTier.SAFE,
    
    # Features
    "PoolPrivateYN": FieldTier.SAFE,
    "SpaYN": FieldTier.SAFE,
    "FireplacesTotal": FieldTier.SAFE,
    "FireplaceYN": FieldTier.SAFE,
    "Cooling": FieldTier.SAFE,
    "Heating": FieldTier.SAFE,
    "ArchitecturalStyle": FieldTier.SAFE,
    "FoundationType": FieldTier.SAFE,
    "Roof": FieldTier.SAFE,
    "ConstructionMaterials": FieldTier.SAFE,
    
    # Location (public)
    "City": FieldTier.SAFE,
    "StateOrProvince": FieldTier.SAFE,
    "PostalCode": FieldTier.SAFE,
    "Country": FieldTier.SAFE,
    "CountyOrParish": FieldTier.SAFE,
    "Latitude": FieldTier.SAFE,
    "Longitude": FieldTier.SAFE,
    "Directions": FieldTier.SAFE,
    
    # Status
    "StandardStatus": FieldTier.SAFE,
    "MlsStatus": FieldTier.SAFE,
    
    # School
    "ElementarySchool": FieldTier.SAFE,
    "MiddleOrJuniorSchool": FieldTier.SAFE,
    "HighSchool": FieldTier.SAFE,
    "SchoolDistrict": FieldTier.SAFE,
    
    # HOA (amounts only, not contacts)
    "AssociationFee": FieldTier.SAFE,
    "AssociationFeeFrequency": FieldTier.SAFE,
    "AssociationYN": FieldTier.SAFE,
    
    # === TIER 1: PUBLIC REMARKS ===
    # May contain PII, agent names, or showing instructions
    "PublicRemarks": FieldTier.PUBLIC_REMARKS,
    "SyndicationRemarks": FieldTier.PUBLIC_REMARKS,
    "Disclaimer": FieldTier.PUBLIC_REMARKS,
    
    # === TIER 2: RESTRICTED ===
    # Agent/broker information - NEVER to LLM
    "ListAgentKey": FieldTier.RESTRICTED,
    "ListAgentMlsId": FieldTier.RESTRICTED,
    "ListAgentFullName": FieldTier.RESTRICTED,
    "ListAgentFirstName": FieldTier.RESTRICTED,
    "ListAgentLastName": FieldTier.RESTRICTED,
    "ListAgentEmail": FieldTier.RESTRICTED,
    "ListAgentDirectPhone": FieldTier.RESTRICTED,
    "ListAgentOfficePhone": FieldTier.RESTRICTED,
    "ListOfficeKey": FieldTier.RESTRICTED,
    "ListOfficeMlsId": FieldTier.RESTRICTED,
    "ListOfficeName": FieldTier.RESTRICTED,
    "ListOfficePhone": FieldTier.RESTRICTED,
    "BuyerAgentKey": FieldTier.RESTRICTED,
    "BuyerAgentMlsId": FieldTier.RESTRICTED,
    "BuyerAgentFullName": FieldTier.RESTRICTED,
    "BuyerAgentEmail": FieldTier.RESTRICTED,
    "BuyerAgentDirectPhone": FieldTier.RESTRICTED,
    "BuyerOfficeKey": FieldTier.RESTRICTED,
    "BuyerOfficeMlsId": FieldTier.RESTRICTED,
    "BuyerOfficeName": FieldTier.RESTRICTED,
    "PrivateRemarks": FieldTier.RESTRICTED,
    "ShowingInstructions": FieldTier.RESTRICTED,
    "LockBoxType": FieldTier.RESTRICTED,
    "LockBoxSerialNumber": FieldTier.RESTRICTED,
    
    # === TIER 3: CONFIDENTIAL ===
    # Owner/tax info - NEVER exposed externally
    "OwnerName": FieldTier.CONFIDENTIAL,
    "OwnerPhone": FieldTier.CONFIDENTIAL,
    "OwnerEmail": FieldTier.CONFIDENTIAL,
    "TaxAnnualAmount": FieldTier.CONFIDENTIAL,
    "TaxAssessedValue": FieldTier.CONFIDENTIAL,
    "TaxLot": FieldTier.CONFIDENTIAL,
    "TaxBlock": FieldTier.CONFIDENTIAL,
    "ParcelNumber": FieldTier.CONFIDENTIAL,
    "TaxLegalDescription": FieldTier.CONFIDENTIAL,
}


def get_field_tier(field_name: str) -> FieldTier:
    """
    Get the tier for a field. Unknown fields default to RESTRICTED.
    """
    return FIELD_TIER_MAP.get(field_name, FieldTier.RESTRICTED)


def filter_fields_for_tier(
    data: dict,
    max_tier: FieldTier = FieldTier.SAFE
) -> dict:
    """
    Filter a data dict to only include fields at or below the max tier.
    
    Args:
        data: Source data dictionary
        max_tier: Maximum tier to include
        
    Returns:
        Filtered dictionary with only allowed fields
    """
    return {
        k: v for k, v in data.items()
        if get_field_tier(k).value <= max_tier.value
    }


def get_llm_safe_fields() -> set[str]:
    """Return set of all fields safe to send to LLM (Tier 0)."""
    return {
        field for field, tier in FIELD_TIER_MAP.items()
        if tier == FieldTier.SAFE
    }


def get_llm_allowed_fields(include_remarks: bool = False) -> set[str]:
    """
    Return set of fields allowed in LLM context.
    
    Args:
        include_remarks: Whether to include Tier 1 (public remarks)
    """
    max_tier = FieldTier.PUBLIC_REMARKS if include_remarks else FieldTier.SAFE
    return {
        field for field, tier in FIELD_TIER_MAP.items()
        if tier.value <= max_tier.value
    }


@dataclass
class BackendCapability:
    """Describes what a data backend can do."""
    
    supports_geo_search: bool = False
    supports_full_text_search: bool = False
    supports_odata_filter: bool = False
    supports_pagination: bool = False
    max_results_per_request: int = 200
    available_fields: set[str] | None = None
    
    def can_execute_filter(self, filter_field: str) -> bool:
        """Check if backend can filter on a field."""
        if self.available_fields is None:
            return True
        return filter_field in self.available_fields


# Capability matrix for each backend
BACKEND_CAPABILITIES: dict[str, BackendCapability] = {
    "reso_mock": BackendCapability(
        supports_geo_search=True,
        supports_full_text_search=True,
        supports_odata_filter=True,
        supports_pagination=True,
        max_results_per_request=200,
    ),
    "csv": BackendCapability(
        supports_geo_search=False,
        supports_full_text_search=True,
        supports_odata_filter=False,
        supports_pagination=True,
        max_results_per_request=200,
    ),
    "reso_real": BackendCapability(
        supports_geo_search=True,
        supports_full_text_search=True,
        supports_odata_filter=True,
        supports_pagination=True,
        max_results_per_request=200,
    ),
}


def get_backend_capability(backend_name: str) -> BackendCapability:
    """Get capabilities for a backend."""
    return BACKEND_CAPABILITIES.get(
        backend_name,
        BackendCapability()  # Conservative default
    )


# Query bounds (ABSOLUTE LIMITS)
MAX_CANDIDATE_RESULTS = 200
MAX_SELECTED_COMPS = 20
MAX_SEARCH_RADIUS_MILES = 5.0
MAX_SALE_AGE_YEARS = 5
MAX_FILTERS_PER_QUERY = 20
MAX_FIELDS_PER_SELECT = 50


def validate_query_bounds(
    max_results: int,
    radius_miles: float | None = None,
    filter_count: int = 0,
    select_count: int = 0
) -> list[str]:
    """
    Validate query parameters against absolute limits.
    
    Returns list of violation messages (empty if valid).
    """
    violations = []
    
    if max_results > MAX_CANDIDATE_RESULTS:
        violations.append(
            f"max_results {max_results} exceeds hard cap of {MAX_CANDIDATE_RESULTS}"
        )
    
    if radius_miles is not None and radius_miles > MAX_SEARCH_RADIUS_MILES:
        violations.append(
            f"radius_miles {radius_miles} exceeds limit of {MAX_SEARCH_RADIUS_MILES}"
        )
    
    if filter_count > MAX_FILTERS_PER_QUERY:
        violations.append(
            f"filter_count {filter_count} exceeds limit of {MAX_FILTERS_PER_QUERY}"
        )
    
    if select_count > MAX_FIELDS_PER_SELECT:
        violations.append(
            f"select_count {select_count} exceeds limit of {MAX_FIELDS_PER_SELECT}"
        )
    
    return violations


class PolicyViolationError(Exception):
    """Raised when a policy is violated."""
    
    def __init__(self, violations: list[str]):
        self.violations = violations
        message = "Policy violations: " + "; ".join(violations)
        super().__init__(message)
