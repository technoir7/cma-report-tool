"""
IntentIR: Intermediate Representation for parsed realtor notes.

This model represents the structured output from LLM parsing of unstructured
realtor notes. All fields have strict bounds to prevent injection of invalid
or out-of-range values.

CRITICAL: The LLM that produces IntentIR must NEVER invent values.
Missing or unclear information must be represented as None/null.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class IntentIR(BaseModel):
    """
    Intermediate representation of a CMA request extracted from realtor notes.
    
    All bounds are enforced at validation time. Invalid values will raise
    ValidationError and must not be silently corrected.
    """
    
    # Subject property identification (optional - notes may not include full address)
    subject_address: str | None = Field(
        default=None,
        min_length=0,  # Changed from 5 to allow empty strings
        max_length=200,
        description="Street address of subject property"
    )
    subject_city: str | None = Field(
        default=None,
        min_length=0,  # Changed from 2 to allow empty strings
        max_length=100,
        description="City of subject property"
    )
    subject_state: str | None = Field(
        default=None,
        min_length=0,  # Changed from 2 to allow empty strings
        max_length=2,
        pattern=r"^([A-Z]{2})?$",  # Optional pattern (empty or 2 uppercase)
        description="Two-letter state code (uppercase)"
    )
    subject_zip: str | None = Field(
        default=None,
        min_length=0,  # Changed from 5 to allow empty strings
        max_length=10,
        pattern=r"^(\d{5}(-\d{4})?)?$",  # Optional pattern (empty or zip)
        description="ZIP code (5-digit or ZIP+4)"
    )
    
    # Subject property characteristics (optional, bounded)
    subject_beds: int | None = Field(
        default=None,
        ge=0,
        le=20,
        description="Number of bedrooms (0-20)"
    )
    subject_baths: float | None = Field(
        default=None,
        ge=0.0,
        le=15.0,
        description="Number of bathrooms including half baths (0-15)"
    )
    subject_sqft: int | None = Field(
        default=None,
        ge=100,
        le=50000,
        description="Living area in square feet (100-50000)"
    )
    subject_lot_sqft: int | None = Field(
        default=None,
        ge=0,
        le=5000000,
        description="Lot size in square feet (0-5000000)"
    )
    subject_year_built: int | None = Field(
        default=None,
        ge=1800,
        le=2030,
        description="Year built (1800-2030)"
    )
    
    # Property type
    property_type: Literal["SFR", "Condo", "Townhouse", "Multi"] | None = Field(
        default=None,
        description="Property type classification"
    )
    
    # Search parameters (bounded)
    search_radius_miles: float = Field(
        default=1.0,
        ge=0.1,
        le=5.0,
        description="Search radius in miles (0.1-5.0)"
    )
    price_range_min: int | None = Field(
        default=None,
        ge=0,
        le=100000000,
        description="Minimum price filter"
    )
    price_range_max: int | None = Field(
        default=None,
        ge=0,
        le=100000000,
        description="Maximum price filter"
    )
    sqft_tolerance_pct: float = Field(
        default=0.15,
        ge=0.0,
        le=0.5,
        description="Square footage tolerance percentage (0-0.5)"
    )
    max_age_years: int = Field(
        default=1,
        ge=0,
        le=5,
        description="Maximum age of comparable sales in years (0-5)"
    )
    
    # Special features (bounded list)
    special_features: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Special features to match (max 10)"
    )
    
    @field_validator("subject_state")
    @classmethod
    def validate_state_uppercase(cls, v: str | None) -> str | None:
        """Ensure state code is uppercase if provided."""
        if v is None:
            return None
        return v.upper()
    
    @field_validator("special_features")
    @classmethod
    def validate_special_features(cls, v: list[str]) -> list[str]:
        """Validate and normalize special features."""
        if len(v) > 10:
            raise ValueError("Maximum 10 special features allowed")
        # Normalize to lowercase, strip whitespace
        return [f.strip().lower() for f in v if f.strip()]
    
    @model_validator(mode="after")
    def validate_price_range(self) -> "IntentIR":
        """Ensure price_range_min <= price_range_max if both provided."""
        if self.price_range_min is not None and self.price_range_max is not None:
            if self.price_range_min > self.price_range_max:
                raise ValueError("price_range_min must be <= price_range_max")
        return self
    
    @model_validator(mode="before")
    @classmethod
    def coerce_defaults(cls, values: dict) -> dict:
        """Ensure fields with defaults have valid values if missing, null, or out of range."""
        if isinstance(values, dict):
            # sqft_tolerance_pct: default 0.15, clamp to [0.0, 0.5]
            sqft_tol = values.get("sqft_tolerance_pct")
            if sqft_tol is None:
                values["sqft_tolerance_pct"] = 0.15
            elif isinstance(sqft_tol, (int, float)):
                values["sqft_tolerance_pct"] = max(0.0, min(0.5, sqft_tol))
            
            # max_age_years: default 1, clamp to [0, 5]
            max_age = values.get("max_age_years")
            if max_age is None:
                values["max_age_years"] = 1
            elif isinstance(max_age, int):
                values["max_age_years"] = max(0, min(5, max_age))
            
            # search_radius_miles: default 1.0, clamp to [0.1, 5.0]
            radius = values.get("search_radius_miles")
            if radius is None:
                values["search_radius_miles"] = 1.0
            elif isinstance(radius, (int, float)):
                values["search_radius_miles"] = max(0.1, min(5.0, radius))
        return values
    
    def get_sqft_range(self) -> tuple[int | None, int | None]:
        """Calculate sqft search range based on subject and tolerance."""
        if self.subject_sqft is None:
            return (None, None)
        min_sqft = int(self.subject_sqft * (1 - self.sqft_tolerance_pct))
        max_sqft = int(self.subject_sqft * (1 + self.sqft_tolerance_pct))
        return (min_sqft, max_sqft)
    
    def to_search_criteria(self) -> dict:
        """
        Convert to neutral search criteria dict.
        
        This is used by connectors to build backend-specific queries.
        """
        sqft_min, sqft_max = self.get_sqft_range()
        
        return {
            "city": self.subject_city,
            "state": self.subject_state,
            "zip": self.subject_zip,
            "property_type": self.property_type,
            "beds_min": self.subject_beds - 1 if self.subject_beds else None,
            "beds_max": self.subject_beds + 1 if self.subject_beds else None,
            "baths_min": self.subject_baths - 0.5 if self.subject_baths else None,
            "baths_max": self.subject_baths + 0.5 if self.subject_baths else None,
            "sqft_min": sqft_min,
            "sqft_max": sqft_max,
            "price_min": self.price_range_min,
            "price_max": self.price_range_max,
            "radius_miles": self.search_radius_miles,
            "max_age_years": self.max_age_years,
            "special_features": self.special_features,
        }


class IntentValidationError(Exception):
    """Raised when IntentIR validation fails."""
    
    def __init__(self, message: str, field: str | None = None):
        self.message = message
        self.field = field
        super().__init__(message)
