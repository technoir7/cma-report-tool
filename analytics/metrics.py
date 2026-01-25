"""
Metrics: Deterministic property valuation calculations.

All calculations in this module are DETERMINISTIC and use only
the data provided. No external data sources or AI inference.

Standard adjustments follow appraisal industry practices:
- GLA (Gross Living Area): $50-100/sqft adjustment
- Bedroom count: $5,000-15,000 per bedroom
- Bathroom count: $3,000-10,000 per bathroom
- Age: 0.5-1% per year difference
- Lot size: Varies by market
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


@dataclass
class AdjustmentConfig:
    """Configuration for property adjustments."""
    
    # Price per sqft adjustment (per sqft difference)
    gla_adjustment_per_sqft: Decimal = Decimal("75")
    
    # Bedroom adjustment (per bedroom difference)
    bedroom_adjustment: Decimal = Decimal("10000")
    
    # Bathroom adjustment (per bathroom difference)
    bathroom_adjustment: Decimal = Decimal("7500")
    
    # Age adjustment (percentage per year)
    age_adjustment_pct_per_year: Decimal = Decimal("0.005")
    
    # Maximum age adjustment (cap at 10%)
    max_age_adjustment_pct: Decimal = Decimal("0.10")
    
    # Lot size adjustment (per sqft difference, if significant)
    lot_adjustment_per_sqft: Decimal = Decimal("1")
    lot_size_threshold_pct: Decimal = Decimal("0.20")  # Only adjust if >20% different
    
    # Garage adjustment (per space)
    garage_adjustment_per_space: Decimal = Decimal("5000")
    
    # Pool adjustment (if subject has, comp doesn't or vice versa)
    pool_adjustment: Decimal = Decimal("15000")


def calculate_price_per_sqft(
    price: int | Decimal,
    sqft: int | None,
    precision: int = 2
) -> Decimal | None:
    """
    Calculate price per square foot.
    
    Args:
        price: Sale price
        sqft: Living area in sqft
        precision: Decimal places to round to
        
    Returns:
        Price per sqft or None if sqft not available
    """
    if sqft is None or sqft <= 0:
        return None
    
    price_decimal = Decimal(str(price))
    sqft_decimal = Decimal(str(sqft))
    
    ppsf = price_decimal / sqft_decimal
    return ppsf.quantize(Decimal(10) ** -precision, rounding=ROUND_HALF_UP)


def calculate_gla_adjustment(
    subject_sqft: int | None,
    comp_sqft: int | None,
    config: AdjustmentConfig | None = None
) -> Decimal:
    """
    Calculate Gross Living Area adjustment.
    
    Positive adjustment means comp is worth MORE than subject
    (comp has smaller GLA, so we add value to make it comparable)
    
    Args:
        subject_sqft: Subject property sqft
        comp_sqft: Comparable property sqft
        config: Adjustment configuration
        
    Returns:
        Adjustment amount (positive = add to comp price)
    """
    if subject_sqft is None or comp_sqft is None:
        return Decimal("0")
    
    config = config or AdjustmentConfig()
    
    sqft_diff = Decimal(str(subject_sqft - comp_sqft))
    adjustment = sqft_diff * config.gla_adjustment_per_sqft
    
    return adjustment.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_bedroom_adjustment(
    subject_beds: int | None,
    comp_beds: int | None,
    config: AdjustmentConfig | None = None
) -> Decimal:
    """
    Calculate bedroom count adjustment.
    
    Args:
        subject_beds: Subject bedroom count
        comp_beds: Comp bedroom count
        config: Adjustment configuration
        
    Returns:
        Adjustment amount
    """
    if subject_beds is None or comp_beds is None:
        return Decimal("0")
    
    config = config or AdjustmentConfig()
    
    bed_diff = subject_beds - comp_beds
    adjustment = Decimal(str(bed_diff)) * config.bedroom_adjustment
    
    return adjustment.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_bathroom_adjustment(
    subject_baths: float | None,
    comp_baths: float | None,
    config: AdjustmentConfig | None = None
) -> Decimal:
    """
    Calculate bathroom count adjustment.
    
    Args:
        subject_baths: Subject bathroom count (can be decimal, e.g., 2.5)
        comp_baths: Comp bathroom count
        config: Adjustment configuration
        
    Returns:
        Adjustment amount
    """
    if subject_baths is None or comp_baths is None:
        return Decimal("0")
    
    config = config or AdjustmentConfig()
    
    bath_diff = Decimal(str(subject_baths)) - Decimal(str(comp_baths))
    adjustment = bath_diff * config.bathroom_adjustment
    
    return adjustment.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_age_adjustment(
    subject_year: int | None,
    comp_year: int | None,
    comp_price: int | Decimal,
    config: AdjustmentConfig | None = None
) -> Decimal:
    """
    Calculate age adjustment based on year built.
    
    Newer properties are generally worth more.
    
    Args:
        subject_year: Subject year built
        comp_year: Comp year built
        comp_price: Comp sale price (for percentage calculation)
        config: Adjustment configuration
        
    Returns:
        Adjustment amount
    """
    if subject_year is None or comp_year is None:
        return Decimal("0")
    
    config = config or AdjustmentConfig()
    
    year_diff = subject_year - comp_year  # Positive if subject is newer
    
    # Calculate percentage adjustment
    pct_adjustment = Decimal(str(year_diff)) * config.age_adjustment_pct_per_year
    
    # Cap at maximum
    if pct_adjustment > config.max_age_adjustment_pct:
        pct_adjustment = config.max_age_adjustment_pct
    elif pct_adjustment < -config.max_age_adjustment_pct:
        pct_adjustment = -config.max_age_adjustment_pct
    
    adjustment = Decimal(str(comp_price)) * pct_adjustment
    
    return adjustment.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_lot_adjustment(
    subject_lot_sqft: int | None,
    comp_lot_sqft: int | None,
    config: AdjustmentConfig | None = None
) -> Decimal:
    """
    Calculate lot size adjustment.
    
    Only applies if difference exceeds threshold.
    
    Args:
        subject_lot_sqft: Subject lot size
        comp_lot_sqft: Comp lot size
        config: Adjustment configuration
        
    Returns:
        Adjustment amount
    """
    if subject_lot_sqft is None or comp_lot_sqft is None:
        return Decimal("0")
    
    if subject_lot_sqft == 0 or comp_lot_sqft == 0:
        return Decimal("0")
    
    config = config or AdjustmentConfig()
    
    # Check if difference exceeds threshold
    pct_diff = abs(subject_lot_sqft - comp_lot_sqft) / max(subject_lot_sqft, comp_lot_sqft)
    if Decimal(str(pct_diff)) < config.lot_size_threshold_pct:
        return Decimal("0")
    
    sqft_diff = Decimal(str(subject_lot_sqft - comp_lot_sqft))
    adjustment = sqft_diff * config.lot_adjustment_per_sqft
    
    return adjustment.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_garage_adjustment(
    subject_garage: int | None,
    comp_garage: int | None,
    config: AdjustmentConfig | None = None
) -> Decimal:
    """
    Calculate garage space adjustment.
    
    Args:
        subject_garage: Subject garage spaces
        comp_garage: Comp garage spaces
        config: Adjustment configuration
        
    Returns:
        Adjustment amount
    """
    if subject_garage is None or comp_garage is None:
        return Decimal("0")
    
    config = config or AdjustmentConfig()
    
    space_diff = subject_garage - comp_garage
    adjustment = Decimal(str(space_diff)) * config.garage_adjustment_per_space
    
    return adjustment.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_pool_adjustment(
    subject_pool: bool | None,
    comp_pool: bool | None,
    config: AdjustmentConfig | None = None
) -> Decimal:
    """
    Calculate pool adjustment.
    
    Args:
        subject_pool: Whether subject has pool
        comp_pool: Whether comp has pool
        config: Adjustment configuration
        
    Returns:
        Adjustment amount
    """
    if subject_pool is None or comp_pool is None:
        return Decimal("0")
    
    config = config or AdjustmentConfig()
    
    if subject_pool and not comp_pool:
        # Subject has pool, comp doesn't - add value to comp
        return config.pool_adjustment
    elif not subject_pool and comp_pool:
        # Comp has pool, subject doesn't - subtract value from comp
        return -config.pool_adjustment
    else:
        return Decimal("0")


@dataclass
class CompAdjustments:
    """All adjustments for a comparable property."""
    
    gla: Decimal = Decimal("0")
    bedrooms: Decimal = Decimal("0")
    bathrooms: Decimal = Decimal("0")
    age: Decimal = Decimal("0")
    lot_size: Decimal = Decimal("0")
    garage: Decimal = Decimal("0")
    pool: Decimal = Decimal("0")
    
    @property
    def total(self) -> Decimal:
        """Calculate total adjustment."""
        return (
            self.gla + self.bedrooms + self.bathrooms +
            self.age + self.lot_size + self.garage + self.pool
        )
    
    def to_list(self) -> list[dict[str, Any]]:
        """Convert to list of adjustment items for ReportJSON."""
        from domain.report_schema import AdjustmentItem
        
        items = []
        adjustments = [
            ("GLA", self.gla),
            ("Bedrooms", self.bedrooms),
            ("Bathrooms", self.bathrooms),
            ("Age", self.age),
            ("Lot Size", self.lot_size),
            ("Garage", self.garage),
            ("Pool", self.pool),
        ]
        
        for name, amount in adjustments:
            if amount != Decimal("0"):
                items.append({
                    "factor": name,
                    "amount": abs(amount),
                    "direction": "positive" if amount > 0 else "negative",
                    "explanation": f"{name} adjustment"
                })
        
        return items


def calculate_all_adjustments(
    subject: dict[str, Any],
    comp: dict[str, Any],
    config: AdjustmentConfig | None = None
) -> CompAdjustments:
    """
    Calculate all adjustments for a comp relative to subject.
    
    Args:
        subject: Subject property data (RESO field names)
        comp: Comparable property data
        config: Adjustment configuration
        
    Returns:
        CompAdjustments with all calculated values
    """
    config = config or AdjustmentConfig()
    
    comp_price = comp.get("ClosePrice", 0)
    
    return CompAdjustments(
        gla=calculate_gla_adjustment(
            subject.get("LivingArea"),
            comp.get("LivingArea"),
            config
        ),
        bedrooms=calculate_bedroom_adjustment(
            subject.get("BedroomsTotal"),
            comp.get("BedroomsTotal"),
            config
        ),
        bathrooms=calculate_bathroom_adjustment(
            subject.get("BathroomsTotalInteger"),
            comp.get("BathroomsTotalInteger"),
            config
        ),
        age=calculate_age_adjustment(
            subject.get("YearBuilt"),
            comp.get("YearBuilt"),
            comp_price,
            config
        ),
        lot_size=calculate_lot_adjustment(
            subject.get("LotSizeSquareFeet"),
            comp.get("LotSizeSquareFeet"),
            config
        ),
        garage=calculate_garage_adjustment(
            subject.get("GarageSpaces"),
            comp.get("GarageSpaces"),
            config
        ),
        pool=calculate_pool_adjustment(
            subject.get("PoolPrivateYN"),
            comp.get("PoolPrivateYN"),
            config
        )
    )
