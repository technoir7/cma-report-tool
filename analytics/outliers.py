"""
Outliers: Statistical outlier detection for comparable properties.

This module identifies outliers in the comparable set using standard
statistical methods (IQR and Z-score). Outliers are flagged but not
automatically excluded - the decision to include/exclude is explicit.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any
import statistics


class OutlierReason(str, Enum):
    """Reasons a property may be flagged as an outlier."""
    
    PRICE_IQR = "price_outside_iqr"
    PRICE_ZSCORE = "price_extreme_zscore"
    PPSF_IQR = "price_per_sqft_outside_iqr"
    PPSF_ZSCORE = "price_per_sqft_extreme_zscore"
    DOM_EXTREME = "days_on_market_extreme"
    SQFT_EXTREME = "sqft_significantly_different"


@dataclass
class OutlierResult:
    """Result of outlier analysis for a single property."""
    
    listing_id: str
    is_outlier: bool
    reasons: list[OutlierReason]
    details: dict[str, Any]


@dataclass 
class OutlierConfig:
    """Configuration for outlier detection."""
    
    # IQR multiplier for outlier threshold (1.5 = standard)
    iqr_multiplier: float = 1.5
    
    # Z-score threshold for extreme outliers
    zscore_threshold: float = 2.5
    
    # Maximum acceptable DOM before flagging
    max_dom_threshold: int = 180
    
    # Sqft difference threshold (percentage)
    sqft_diff_threshold: float = 0.50


def calculate_iqr_bounds(values: list[float]) -> tuple[float, float]:
    """
    Calculate IQR-based outlier bounds.
    
    Args:
        values: List of numeric values
        
    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    if len(values) < 4:
        # Not enough data for meaningful IQR
        if not values:
            return (0.0, float('inf'))
        return (min(values) * 0.5, max(values) * 1.5)
    
    sorted_values = sorted(values)
    n = len(sorted_values)
    
    # Calculate Q1 and Q3
    q1_idx = n // 4
    q3_idx = 3 * n // 4
    
    q1 = sorted_values[q1_idx]
    q3 = sorted_values[q3_idx]
    
    iqr = q3 - q1
    
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    
    return (lower, upper)


def calculate_zscore(value: float, values: list[float]) -> float:
    """
    Calculate Z-score for a value.
    
    Args:
        value: Value to calculate Z-score for
        values: Population of values
        
    Returns:
        Z-score (standard deviations from mean)
    """
    if len(values) < 2:
        return 0.0
    
    mean = statistics.mean(values)
    stdev = statistics.stdev(values)
    
    if stdev == 0:
        return 0.0
    
    return (value - mean) / stdev


def detect_price_outliers(
    comps: list[dict[str, Any]],
    config: OutlierConfig | None = None
) -> dict[str, OutlierResult]:
    """
    Detect outliers based on close price.
    
    Args:
        comps: List of comparable properties
        config: Outlier detection configuration
        
    Returns:
        Dict mapping listing_id to OutlierResult
    """
    config = config or OutlierConfig()
    results = {}
    
    # Extract prices
    prices = []
    for comp in comps:
        price = comp.get("ClosePrice")
        if price is not None:
            prices.append(float(price))
    
    if not prices:
        return {}
    
    # Calculate bounds
    lower, upper = calculate_iqr_bounds(prices)
    
    for comp in comps:
        listing_id = comp.get("ListingId", "")
        price = comp.get("ClosePrice")
        
        if price is None:
            continue
        
        price_float = float(price)
        reasons = []
        details = {"price": price}
        
        # Check IQR
        if price_float < lower or price_float > upper:
            reasons.append(OutlierReason.PRICE_IQR)
            details["iqr_bounds"] = (lower, upper)
        
        # Check Z-score
        zscore = calculate_zscore(price_float, prices)
        details["zscore"] = zscore
        if abs(zscore) > config.zscore_threshold:
            reasons.append(OutlierReason.PRICE_ZSCORE)
        
        results[listing_id] = OutlierResult(
            listing_id=listing_id,
            is_outlier=len(reasons) > 0,
            reasons=reasons,
            details=details
        )
    
    return results


def detect_ppsf_outliers(
    comps: list[dict[str, Any]],
    config: OutlierConfig | None = None
) -> dict[str, OutlierResult]:
    """
    Detect outliers based on price per square foot.
    
    Args:
        comps: List of comparable properties
        config: Outlier detection configuration
        
    Returns:
        Dict mapping listing_id to OutlierResult
    """
    config = config or OutlierConfig()
    results = {}
    
    # Calculate PPSF for each comp
    ppsf_values = []
    ppsf_map = {}
    
    for comp in comps:
        price = comp.get("ClosePrice")
        sqft = comp.get("LivingArea")
        listing_id = comp.get("ListingId", "")
        
        if price is not None and sqft is not None and sqft > 0:
            ppsf = float(price) / float(sqft)
            ppsf_values.append(ppsf)
            ppsf_map[listing_id] = ppsf
    
    if not ppsf_values:
        return {}
    
    lower, upper = calculate_iqr_bounds(ppsf_values)
    
    for listing_id, ppsf in ppsf_map.items():
        reasons = []
        details = {"price_per_sqft": ppsf}
        
        if ppsf < lower or ppsf > upper:
            reasons.append(OutlierReason.PPSF_IQR)
            details["iqr_bounds"] = (lower, upper)
        
        zscore = calculate_zscore(ppsf, ppsf_values)
        details["zscore"] = zscore
        if abs(zscore) > config.zscore_threshold:
            reasons.append(OutlierReason.PPSF_ZSCORE)
        
        results[listing_id] = OutlierResult(
            listing_id=listing_id,
            is_outlier=len(reasons) > 0,
            reasons=reasons,
            details=details
        )
    
    return results


def detect_dom_outliers(
    comps: list[dict[str, Any]],
    config: OutlierConfig | None = None
) -> dict[str, OutlierResult]:
    """
    Detect outliers based on days on market.
    
    Args:
        comps: List of comparable properties
        config: Outlier detection configuration
        
    Returns:
        Dict mapping listing_id to OutlierResult
    """
    config = config or OutlierConfig()
    results = {}
    
    for comp in comps:
        listing_id = comp.get("ListingId", "")
        dom = comp.get("DaysOnMarket")
        
        if dom is None:
            continue
        
        dom_int = int(dom)
        reasons = []
        details = {"days_on_market": dom_int}
        
        if dom_int > config.max_dom_threshold:
            reasons.append(OutlierReason.DOM_EXTREME)
            details["threshold"] = config.max_dom_threshold
        
        results[listing_id] = OutlierResult(
            listing_id=listing_id,
            is_outlier=len(reasons) > 0,
            reasons=reasons,
            details=details
        )
    
    return results


def detect_sqft_outliers(
    subject_sqft: int | None,
    comps: list[dict[str, Any]],
    config: OutlierConfig | None = None
) -> dict[str, OutlierResult]:
    """
    Detect outliers based on sqft difference from subject.
    
    Args:
        subject_sqft: Subject property square footage
        comps: List of comparable properties
        config: Outlier detection configuration
        
    Returns:
        Dict mapping listing_id to OutlierResult
    """
    config = config or OutlierConfig()
    results = {}
    
    if subject_sqft is None or subject_sqft <= 0:
        return {}
    
    for comp in comps:
        listing_id = comp.get("ListingId", "")
        comp_sqft = comp.get("LivingArea")
        
        if comp_sqft is None:
            continue
        
        pct_diff = abs(subject_sqft - comp_sqft) / subject_sqft
        reasons = []
        details = {
            "comp_sqft": comp_sqft,
            "subject_sqft": subject_sqft,
            "pct_difference": pct_diff
        }
        
        if pct_diff > config.sqft_diff_threshold:
            reasons.append(OutlierReason.SQFT_EXTREME)
            details["threshold"] = config.sqft_diff_threshold
        
        results[listing_id] = OutlierResult(
            listing_id=listing_id,
            is_outlier=len(reasons) > 0,
            reasons=reasons,
            details=details
        )
    
    return results


def detect_all_outliers(
    subject: dict[str, Any],
    comps: list[dict[str, Any]],
    config: OutlierConfig | None = None
) -> dict[str, OutlierResult]:
    """
    Run all outlier detection methods and combine results.
    
    Args:
        subject: Subject property data
        comps: List of comparable properties
        config: Outlier detection configuration
        
    Returns:
        Combined outlier results for all comps
    """
    config = config or OutlierConfig()
    
    # Run all detection methods
    price_results = detect_price_outliers(comps, config)
    ppsf_results = detect_ppsf_outliers(comps, config)
    dom_results = detect_dom_outliers(comps, config)
    sqft_results = detect_sqft_outliers(
        subject.get("LivingArea"),
        comps,
        config
    )
    
    # Combine results
    combined = {}
    all_ids = set(price_results.keys()) | set(ppsf_results.keys()) | \
              set(dom_results.keys()) | set(sqft_results.keys())
    
    for listing_id in all_ids:
        reasons = []
        details = {}
        
        for result_dict in [price_results, ppsf_results, dom_results, sqft_results]:
            if listing_id in result_dict:
                result = result_dict[listing_id]
                reasons.extend(result.reasons)
                details.update(result.details)
        
        combined[listing_id] = OutlierResult(
            listing_id=listing_id,
            is_outlier=len(reasons) > 0,
            reasons=reasons,
            details=details
        )
    
    return combined


def get_outlier_summary(results: dict[str, OutlierResult]) -> dict[str, Any]:
    """
    Generate summary statistics about outliers.
    
    Args:
        results: Outlier detection results
        
    Returns:
        Summary dict with counts and breakdown
    """
    total = len(results)
    outliers = sum(1 for r in results.values() if r.is_outlier)
    
    reason_counts = {}
    for result in results.values():
        for reason in result.reasons:
            reason_counts[reason.value] = reason_counts.get(reason.value, 0) + 1
    
    return {
        "total_analyzed": total,
        "outlier_count": outliers,
        "outlier_pct": (outliers / total * 100) if total > 0 else 0,
        "reason_breakdown": reason_counts
    }
