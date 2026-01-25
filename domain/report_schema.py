"""
ReportJSON: Structured report data with provenance tracking.

This module defines the complete report schema that serves as the ONLY
source of truth for report generation. The LLM receives this structure
and must render narrative ONLY from values present here.

CRITICAL: The allowed_values field contains every numeric value that
may appear in the generated report. Any number not in this set is
a hallucination and must cause report rejection.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field, model_validator


class AddressInfo(BaseModel):
    """Standardized address representation."""
    
    street: str
    city: str
    state: str = Field(min_length=2, max_length=2)
    zip_code: str
    county: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class PropertyCharacteristics(BaseModel):
    """Physical characteristics of a property."""
    
    property_type: str
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    bathrooms: float | None = Field(default=None, ge=0, le=15)
    living_area_sqft: int | None = Field(default=None, ge=0, le=100000)
    lot_size_sqft: int | None = Field(default=None, ge=0, le=5000000)
    year_built: int | None = Field(default=None, ge=1800, le=2030)
    stories: int | None = Field(default=None, ge=1, le=10)
    garage_spaces: int | None = Field(default=None, ge=0, le=10)
    pool: bool | None = None
    
    def get_numeric_values(self) -> set[Decimal]:
        """Extract all numeric values for hallucination check."""
        values = set()
        if self.bedrooms is not None:
            values.add(Decimal(str(self.bedrooms)))
        if self.bathrooms is not None:
            values.add(Decimal(str(self.bathrooms)))
        if self.living_area_sqft is not None:
            values.add(Decimal(str(self.living_area_sqft)))
        if self.lot_size_sqft is not None:
            values.add(Decimal(str(self.lot_size_sqft)))
        if self.year_built is not None:
            values.add(Decimal(str(self.year_built)))
        if self.stories is not None:
            values.add(Decimal(str(self.stories)))
        if self.garage_spaces is not None:
            values.add(Decimal(str(self.garage_spaces)))
        return values


class SubjectProperty(BaseModel):
    """The subject property being appraised/evaluated."""
    
    address: AddressInfo
    characteristics: PropertyCharacteristics
    estimated_value: Decimal | None = None
    value_range_low: Decimal | None = None
    value_range_high: Decimal | None = None
    
    def get_numeric_values(self) -> set[Decimal]:
        """Extract all numeric values for hallucination check."""
        values = self.characteristics.get_numeric_values()
        if self.estimated_value is not None:
            values.add(self.estimated_value)
        if self.value_range_low is not None:
            values.add(self.value_range_low)
        if self.value_range_high is not None:
            values.add(self.value_range_high)
        if self.address.latitude is not None:
            values.add(Decimal(str(self.address.latitude)))
        if self.address.longitude is not None:
            values.add(Decimal(str(self.address.longitude)))
        return values


class SaleInfo(BaseModel):
    """Sale transaction information."""
    
    close_price: Decimal
    close_date: datetime
    original_list_price: Decimal | None = None
    days_on_market: int | None = Field(default=None, ge=0)
    
    def get_numeric_values(self) -> set[Decimal]:
        """Extract all numeric values for hallucination check."""
        values = {self.close_price}
        if self.original_list_price is not None:
            values.add(self.original_list_price)
        if self.days_on_market is not None:
            values.add(Decimal(str(self.days_on_market)))
        return values


class AdjustmentItem(BaseModel):
    """A single adjustment applied to a comp."""
    
    factor: str  # e.g., "GLA", "Bedrooms", "Age"
    amount: Decimal
    direction: Literal["positive", "negative"]
    explanation: str
    
    def get_numeric_values(self) -> set[Decimal]:
        """Extract all numeric values for hallucination check."""
        return {self.amount, abs(self.amount)}


class CompProperty(BaseModel):
    """A comparable property with adjustments."""
    
    listing_id: str
    address: AddressInfo
    characteristics: PropertyCharacteristics
    sale_info: SaleInfo
    
    # Distance from subject
    distance_miles: Decimal
    
    # Similarity score (0-100)
    similarity_score: Decimal = Field(ge=0, le=100)
    
    # Adjustments applied
    adjustments: list[AdjustmentItem] = Field(default_factory=list)
    
    # Computed adjusted price
    adjusted_price: Decimal
    
    # Price per sqft
    price_per_sqft: Decimal | None = None
    adjusted_price_per_sqft: Decimal | None = None
    
    # Outlier flag
    is_outlier: bool = False
    outlier_reason: str | None = None
    
    def get_numeric_values(self) -> set[Decimal]:
        """Extract all numeric values for hallucination check."""
        values = self.characteristics.get_numeric_values()
        values.update(self.sale_info.get_numeric_values())
        values.add(self.distance_miles)
        values.add(self.similarity_score)
        values.add(self.adjusted_price)
        
        if self.price_per_sqft is not None:
            values.add(self.price_per_sqft)
        if self.adjusted_price_per_sqft is not None:
            values.add(self.adjusted_price_per_sqft)
        
        for adj in self.adjustments:
            values.update(adj.get_numeric_values())
        
        if self.address.latitude is not None:
            values.add(Decimal(str(self.address.latitude)))
        if self.address.longitude is not None:
            values.add(Decimal(str(self.address.longitude)))
        
        return values


class AnalyticsSection(BaseModel):
    """Computed analytics for the CMA report."""
    
    # Value estimates
    indicated_value: Decimal
    value_range_low: Decimal
    value_range_high: Decimal
    confidence_score: Decimal = Field(ge=0, le=100)
    
    # Price statistics
    median_price: Decimal
    mean_price: Decimal
    price_std_dev: Decimal
    
    # Price per sqft statistics
    median_price_per_sqft: Decimal
    mean_price_per_sqft: Decimal
    
    # Adjusted price statistics
    median_adjusted_price: Decimal
    mean_adjusted_price: Decimal
    
    # Market conditions
    avg_days_on_market: Decimal
    
    # Comp summary
    total_comps_analyzed: int = Field(ge=0)
    outliers_excluded: int = Field(default=0, ge=0)
    
    def get_numeric_values(self) -> set[Decimal]:
        """Extract all numeric values for hallucination check."""
        return {
            self.indicated_value,
            self.value_range_low,
            self.value_range_high,
            self.confidence_score,
            self.median_price,
            self.mean_price,
            self.price_std_dev,
            self.median_price_per_sqft,
            self.mean_price_per_sqft,
            self.median_adjusted_price,
            self.mean_adjusted_price,
            self.avg_days_on_market,
            Decimal(str(self.total_comps_analyzed)),
            Decimal(str(self.outliers_excluded)),
        }


class DataLimitation(BaseModel):
    """A documented limitation in the data or analysis."""
    
    category: Literal["data_quality", "sample_size", "geographic", "temporal", "feature_match"]
    description: str
    severity: Literal["info", "warning", "critical"]


class ReportJSON(BaseModel):
    """
    Complete CMA report structure with provenance.
    
    This is the SINGLE SOURCE OF TRUTH for report generation.
    The LLM must render narrative ONLY from values in this structure.
    
    The allowed_values field is computed from all numeric values in the
    report and used for hallucination detection.
    """
    
    # Report metadata
    report_id: UUID = Field(default_factory=uuid4)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    report_version: str = "1.0.0"
    
    # Subject property
    subject: SubjectProperty
    
    # Selected comparables (HARD CAP: 20)
    selected_comps: list[CompProperty] = Field(
        default_factory=list,
        max_length=20
    )
    
    # Analytics
    analytics: AnalyticsSection
    
    # Data limitations (for graceful degradation)
    limitations: list[DataLimitation] = Field(default_factory=list)
    
    # Query provenance
    query_hash: str | None = None
    data_source: str | None = None
    
    @computed_field
    @property
    def allowed_values(self) -> set[Decimal]:
        """
        Compute the set of all numeric values that may appear in the report.
        
        This is used for hallucination detection. Any numeric value in the
        generated narrative that is not in this set is a hallucination.
        """
        values = set()
        
        # Subject values
        values.update(self.subject.get_numeric_values())
        
        # Comp values
        for comp in self.selected_comps:
            values.update(comp.get_numeric_values())
        
        # Analytics values
        values.update(self.analytics.get_numeric_values())
        
        # Add common derived values
        # Percentages (0-100 range integers)
        for i in range(101):
            values.add(Decimal(str(i)))
        
        # Add count of comps
        values.add(Decimal(str(len(self.selected_comps))))
        
        return values
    
    @model_validator(mode="after")
    def validate_comp_count(self) -> "ReportJSON":
        """Enforce hard cap on selected comps."""
        if len(self.selected_comps) > 20:
            raise ValueError("Maximum 20 selected comps allowed (hard cap)")
        return self
    
    def to_llm_context(self) -> str:
        """
        Convert to a structured string for LLM consumption.
        
        This produces a deterministic, formatted representation
        that the LLM uses to generate narrative.
        """
        lines = [
            "=== CMA REPORT DATA ===",
            "",
            "## SUBJECT PROPERTY",
            f"Address: {self.subject.address.street}, {self.subject.address.city}, {self.subject.address.state} {self.subject.address.zip_code}",
        ]
        
        chars = self.subject.characteristics
        if chars.bedrooms is not None:
            lines.append(f"Bedrooms: {chars.bedrooms}")
        if chars.bathrooms is not None:
            lines.append(f"Bathrooms: {chars.bathrooms}")
        if chars.living_area_sqft is not None:
            lines.append(f"Living Area: {chars.living_area_sqft:,} sq ft")
        if chars.lot_size_sqft is not None:
            lines.append(f"Lot Size: {chars.lot_size_sqft:,} sq ft")
        if chars.year_built is not None:
            lines.append(f"Year Built: {chars.year_built}")
        
        lines.extend([
            "",
            "## COMPARABLE SALES",
        ])
        
        for i, comp in enumerate(self.selected_comps, 1):
            lines.extend([
                f"",
                f"### Comp #{i}",
                f"Address: {comp.address.street}, {comp.address.city}",
                f"Close Price: ${comp.sale_info.close_price:,.0f}",
                f"Close Date: {comp.sale_info.close_date.strftime('%Y-%m-%d')}",
                f"Living Area: {comp.characteristics.living_area_sqft:,} sq ft" if comp.characteristics.living_area_sqft else "",
                f"Price/SqFt: ${comp.price_per_sqft:,.2f}" if comp.price_per_sqft else "",
                f"Distance: {comp.distance_miles:.2f} miles",
                f"Similarity Score: {comp.similarity_score:.0f}/100",
                f"Adjusted Price: ${comp.adjusted_price:,.0f}",
            ])
            
            if comp.is_outlier:
                lines.append(f"**OUTLIER**: {comp.outlier_reason}")
        
        lines.extend([
            "",
            "## ANALYTICS",
            f"Indicated Value: ${self.analytics.indicated_value:,.0f}",
            f"Value Range: ${self.analytics.value_range_low:,.0f} - ${self.analytics.value_range_high:,.0f}",
            f"Confidence Score: {self.analytics.confidence_score:.0f}/100",
            f"Median Price: ${self.analytics.median_price:,.0f}",
            f"Mean Price: ${self.analytics.mean_price:,.0f}",
            f"Median Price/SqFt: ${self.analytics.median_price_per_sqft:,.2f}",
            f"Average Days on Market: {self.analytics.avg_days_on_market:.0f}",
            f"Total Comps Analyzed: {self.analytics.total_comps_analyzed}",
        ])
        
        if self.limitations:
            lines.extend([
                "",
                "## DATA LIMITATIONS",
            ])
            for lim in self.limitations:
                lines.append(f"- [{lim.severity.upper()}] {lim.description}")
        
        lines.append("")
        lines.append("=== END REPORT DATA ===")
        
        return "\n".join(lines)
