"""
Ranking: Comparable property similarity scoring.

This module calculates similarity scores to rank comparables
by how closely they match the subject property. All scoring
is deterministic based on property characteristics.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
import math


@dataclass
class SimilarityWeights:
    """Weights for similarity score components."""
    
    # Location/distance weight
    distance: float = 0.25
    
    # Property characteristics
    sqft: float = 0.20
    bedrooms: float = 0.15
    bathrooms: float = 0.10
    year_built: float = 0.10
    
    # Sale characteristics
    recency: float = 0.10
    price: float = 0.10
    
    def total(self) -> float:
        """Verify weights sum to 1.0."""
        return (
            self.distance + self.sqft + self.bedrooms +
            self.bathrooms + self.year_built + self.recency + self.price
        )


def calculate_distance_score(distance_miles: float, max_distance: float = 5.0) -> float:
    """
    Calculate distance similarity score (0-100).
    
    Closer = higher score, using exponential decay.
    
    Args:
        distance_miles: Distance from subject
        max_distance: Maximum search radius
        
    Returns:
        Score 0-100
    """
    if distance_miles <= 0:
        return 100.0
    
    if distance_miles >= max_distance:
        return 0.0
    
    # Exponential decay - distance of 0 = 100, max_distance = ~5
    decay_rate = 3.0 / max_distance  # Decay to ~5% at max distance
    score = 100.0 * math.exp(-decay_rate * distance_miles)
    
    return max(0.0, min(100.0, score))


def calculate_sqft_score(
    subject_sqft: int | None,
    comp_sqft: int | None,
    tolerance_pct: float = 0.20
) -> float:
    """
    Calculate square footage similarity score (0-100).
    
    Perfect match = 100, outside tolerance = 0.
    
    Args:
        subject_sqft: Subject living area
        comp_sqft: Comp living area
        tolerance_pct: Tolerance percentage (e.g., 0.20 = 20%)
        
    Returns:
        Score 0-100
    """
    if subject_sqft is None or comp_sqft is None:
        return 50.0  # Neutral score for missing data
    
    if subject_sqft == 0:
        return 50.0
    
    pct_diff = abs(subject_sqft - comp_sqft) / subject_sqft
    
    if pct_diff == 0:
        return 100.0
    
    if pct_diff >= tolerance_pct:
        # Outside tolerance - linear decay to 0 at 2x tolerance
        if pct_diff >= 2 * tolerance_pct:
            return 0.0
        excess = pct_diff - tolerance_pct
        return max(0.0, 50.0 * (1 - excess / tolerance_pct))
    
    # Within tolerance - linear from 100 to 50
    return 100.0 - (50.0 * pct_diff / tolerance_pct)


def calculate_bedroom_score(
    subject_beds: int | None,
    comp_beds: int | None
) -> float:
    """
    Calculate bedroom count similarity score (0-100).
    
    Args:
        subject_beds: Subject bedroom count
        comp_beds: Comp bedroom count
        
    Returns:
        Score 0-100
    """
    if subject_beds is None or comp_beds is None:
        return 50.0
    
    diff = abs(subject_beds - comp_beds)
    
    scores = {0: 100.0, 1: 75.0, 2: 40.0, 3: 10.0}
    return scores.get(diff, 0.0)


def calculate_bathroom_score(
    subject_baths: float | None,
    comp_baths: float | None
) -> float:
    """
    Calculate bathroom count similarity score (0-100).
    
    Args:
        subject_baths: Subject bathroom count
        comp_baths: Comp bathroom count
        
    Returns:
        Score 0-100
    """
    if subject_baths is None or comp_baths is None:
        return 50.0
    
    diff = abs(subject_baths - comp_baths)
    
    if diff == 0:
        return 100.0
    elif diff <= 0.5:
        return 90.0
    elif diff <= 1.0:
        return 70.0
    elif diff <= 1.5:
        return 40.0
    elif diff <= 2.0:
        return 20.0
    else:
        return 0.0


def calculate_age_score(
    subject_year: int | None,
    comp_year: int | None,
    max_diff_years: int = 20
) -> float:
    """
    Calculate age similarity score (0-100).
    
    Args:
        subject_year: Subject year built
        comp_year: Comp year built
        max_diff_years: Maximum year difference for scoring
        
    Returns:
        Score 0-100
    """
    if subject_year is None or comp_year is None:
        return 50.0
    
    diff = abs(subject_year - comp_year)
    
    if diff == 0:
        return 100.0
    
    if diff >= max_diff_years:
        return 0.0
    
    return 100.0 * (1 - diff / max_diff_years)


def calculate_recency_score(days_since_sale: int, max_days: int = 365) -> float:
    """
    Calculate recency score (0-100).
    
    More recent sales score higher.
    
    Args:
        days_since_sale: Days since the sale closed
        max_days: Maximum days to consider
        
    Returns:
        Score 0-100
    """
    if days_since_sale <= 0:
        return 100.0
    
    if days_since_sale >= max_days:
        return 10.0  # Minimum recency score for old sales
    
    # Linear decay with minimum
    score = 100.0 * (1 - 0.9 * days_since_sale / max_days)
    return max(10.0, score)


def calculate_price_similarity_score(
    estimated_subject_price: int | None,
    comp_price: int | Decimal,
    tolerance_pct: float = 0.30
) -> float:
    """
    Calculate price similarity score (0-100).
    
    Args:
        estimated_subject_price: Estimated subject value (if known)
        comp_price: Comp sale price
        tolerance_pct: Price tolerance percentage
        
    Returns:
        Score 0-100
    """
    if estimated_subject_price is None:
        return 50.0  # Neutral if no estimate
    
    if estimated_subject_price == 0:
        return 50.0
    
    comp_price_int = int(comp_price) if isinstance(comp_price, Decimal) else comp_price
    pct_diff = abs(estimated_subject_price - comp_price_int) / estimated_subject_price
    
    if pct_diff >= tolerance_pct:
        return max(0.0, 50.0 * (1 - (pct_diff - tolerance_pct) / tolerance_pct))
    
    return 100.0 * (1 - pct_diff / tolerance_pct)


@dataclass
class SimilarityResult:
    """Result of similarity calculation."""
    
    total_score: Decimal
    distance_score: float
    sqft_score: float
    bedroom_score: float
    bathroom_score: float
    age_score: float
    recency_score: float
    price_score: float
    

def calculate_similarity_score(
    subject: dict[str, Any],
    comp: dict[str, Any],
    distance_miles: float,
    days_since_sale: int,
    estimated_subject_price: int | None = None,
    weights: SimilarityWeights | None = None,
    sqft_tolerance: float = 0.20
) -> SimilarityResult:
    """
    Calculate overall similarity score for a comparable.
    
    Args:
        subject: Subject property data
        comp: Comparable property data
        distance_miles: Distance from subject to comp
        days_since_sale: Days since comp sale
        estimated_subject_price: Optional estimated subject value
        weights: Scoring weights
        sqft_tolerance: Square footage tolerance
        
    Returns:
        SimilarityResult with total and component scores
    """
    weights = weights or SimilarityWeights()
    
    # Calculate component scores
    distance_score = calculate_distance_score(distance_miles)
    sqft_score = calculate_sqft_score(
        subject.get("LivingArea"),
        comp.get("LivingArea"),
        sqft_tolerance
    )
    bedroom_score = calculate_bedroom_score(
        subject.get("BedroomsTotal"),
        comp.get("BedroomsTotal")
    )
    bathroom_score = calculate_bathroom_score(
        subject.get("BathroomsTotalInteger"),
        comp.get("BathroomsTotalInteger")
    )
    age_score = calculate_age_score(
        subject.get("YearBuilt"),
        comp.get("YearBuilt")
    )
    recency_score = calculate_recency_score(days_since_sale)
    price_score = calculate_price_similarity_score(
        estimated_subject_price,
        comp.get("ClosePrice", 0)
    )
    
    # Calculate weighted total
    total = (
        weights.distance * distance_score +
        weights.sqft * sqft_score +
        weights.bedrooms * bedroom_score +
        weights.bathrooms * bathroom_score +
        weights.year_built * age_score +
        weights.recency * recency_score +
        weights.price * price_score
    )
    
    return SimilarityResult(
        total_score=Decimal(str(total)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
        distance_score=distance_score,
        sqft_score=sqft_score,
        bedroom_score=bedroom_score,
        bathroom_score=bathroom_score,
        age_score=age_score,
        recency_score=recency_score,
        price_score=price_score
    )


def rank_comparables(
    subject: dict[str, Any],
    comps: list[dict[str, Any]],
    distances: dict[str, float],  # listing_id -> distance
    sale_dates: dict[str, int],   # listing_id -> days since sale
    estimated_subject_price: int | None = None,
    limit: int = 20
) -> list[tuple[dict[str, Any], SimilarityResult]]:
    """
    Rank comparables by similarity score.
    
    Args:
        subject: Subject property data
        comps: List of comparable properties
        distances: Map of listing_id to distance in miles
        sale_dates: Map of listing_id to days since sale
        estimated_subject_price: Optional estimated value
        limit: Maximum comps to return
        
    Returns:
        List of (comp, SimilarityResult) sorted by score descending
    """
    scored = []
    
    for comp in comps:
        listing_id = comp.get("ListingId", "")
        distance = distances.get(listing_id, 5.0)
        days = sale_dates.get(listing_id, 365)
        
        result = calculate_similarity_score(
            subject=subject,
            comp=comp,
            distance_miles=distance,
            days_since_sale=days,
            estimated_subject_price=estimated_subject_price
        )
        
        scored.append((comp, result))
    
    # Sort by total score descending
    scored.sort(key=lambda x: x[1].total_score, reverse=True)
    
    # Apply limit (max 20 per policy)
    return scored[:min(limit, 20)]
