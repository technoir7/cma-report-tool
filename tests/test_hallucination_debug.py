"""
Test to debug hallucination detection in report generation.
"""
import pytest
from decimal import Decimal
from datetime import datetime, date
from uuid import uuid4
from unittest.mock import MagicMock, patch

from domain.report_schema import (
    ReportJSON, SubjectProperty, CompProperty, AnalyticsSection,
    AddressInfo, PropertyCharacteristics, SaleInfo, ScoreBreakdown, DataLimitation
)
from llm.report_writer import ReportWriter, HallucinationVerifier, HallucinationError

def create_test_report() -> ReportJSON:
    """Create a minimal valid ReportJSON for testing."""
    subject = SubjectProperty(
        address=AddressInfo(
            street="123 Test St",
            city="Denver",
            state="CO",
            zip_code="80202"
        ),
        characteristics=PropertyCharacteristics(
            property_type="Residential",
            bedrooms=2,
            bathrooms=Decimal("1.0"),
            living_area_sqft=980,
            lot_size_sqft=5000,
            year_built=1948
        )
    )
    
    comp1 = CompProperty(
        listing_id="CMA-REG-01",
        address=AddressInfo(street="456 Comp St", city="Denver", state="CO", zip_code="80202"),
        characteristics=PropertyCharacteristics(
            property_type="Residential",
            bedrooms=2,
            bathrooms=Decimal("1.0"),
            living_area_sqft=980,
            year_built=1948
        ),
        sale_info=SaleInfo(
            close_price=Decimal("455000"),
            close_date=date(2025, 12, 15),
            original_list_price=Decimal("460000"),
            days_on_market=5
        ),
        data_source="csv",
        data_timestamp=datetime.now(),
        distance_miles=Decimal("0.5"),
        similarity_score=Decimal("78"),
        score_breakdown=ScoreBreakdown(
            total_score=Decimal("78"),
            distance_score=Decimal("80"),
            sqft_score=Decimal("100"),
            bedroom_score=Decimal("100"),
            bathroom_score=Decimal("50"),
            age_score=Decimal("50"),
            recency_score=Decimal("90"),
            price_score=Decimal("50")
        ),
        selection_reasons=["Near", "Recent"],
        adjusted_price=Decimal("455000"),
        price_per_sqft=Decimal("464.29"),
        adjusted_price_per_sqft=Decimal("464.29")
    )
    
    analytics = AnalyticsSection(
        indicated_value=Decimal("455000"),
        value_range_low=Decimal("430000"),
        value_range_high=Decimal("480000"),
        confidence_score=Decimal("75"),
        median_price=Decimal("455000"),
        mean_price=Decimal("455000"),
        price_std_dev=Decimal("10000"),
        median_price_per_sqft=Decimal("464"),
        mean_price_per_sqft=Decimal("464"),
        median_adjusted_price=Decimal("455000"),
        mean_adjusted_price=Decimal("455000"),
        avg_days_on_market=Decimal("5"),
        total_comps_analyzed=1,
        outliers_excluded=0
    )
    
    return ReportJSON(
        report_id=uuid4(),
        generated_at=datetime.now(),
        subject=subject,
        selected_comps=[comp1],
        analytics=analytics,
        methodology="test",
        limitations=[DataLimitation(category="data_quality", description="Test only", severity="info")]
    )


def test_allowed_values_contains_price_per_sqft():
    """Verify allowed_values includes price_per_sqft."""
    report = create_test_report()
    allowed = report.allowed_values
    
    # Check price_per_sqft is in allowed
    assert Decimal("464.29") in allowed or Decimal("464") in allowed, \
        f"price_per_sqft not in allowed_values. Sample: {list(allowed)[:20]}"


def test_verifier_allows_legitimate_numbers():
    """Verify legit numbers pass."""
    verifier = HallucinationVerifier()
    text = "The property sold for $455,000, which is $464 per sq ft."
    allowed = {Decimal("455000"), Decimal("464")}
    
    is_valid, hallucinated = verifier.verify(text, allowed)
    assert is_valid, f"Hallucinated: {hallucinated}"


def test_verifier_catches_invented_numbers():
    """Verify invented numbers are caught."""
    verifier = HallucinationVerifier()
    text = "The property sold for $500,000."  # 500000 not in allowed
    allowed = {Decimal("455000"), Decimal("464")}
    
    is_valid, hallucinated = verifier.verify(text, allowed)
    assert not is_valid
    assert Decimal("500000") in hallucinated


def test_report_generation_with_mock_llm():
    """Test generate with a mock LLM that returns valid content."""
    report = create_test_report()
    
    mock_llm = MagicMock()
    mock_llm.complete.return_value = MagicMock(
        content="The subject property sold for $455,000. Price per sqft is $464."
    )
    
    writer = ReportWriter(llm_client=mock_llm, max_retries=1)
    narrative = writer.generate(report)
    
    assert "455,000" in narrative


def test_report_generation_with_hallucinating_llm():
    """Test that hallucinating LLM causes error."""
    report = create_test_report()
    
    mock_llm = MagicMock()
    # LLM invents $999,999
    mock_llm.complete.return_value = MagicMock(
        content="The subject property sold for $999,999."
    )
    
    writer = ReportWriter(llm_client=mock_llm, max_retries=1)
    
    with pytest.raises(HallucinationError) as exc_info:
        writer.generate(report)
    
    assert Decimal("999999") in exc_info.value.hallucinated_values


if __name__ == "__main__":
    test_allowed_values_contains_price_per_sqft()
    test_verifier_allows_legitimate_numbers()
    test_verifier_catches_invented_numbers()
    test_report_generation_with_mock_llm()
    test_report_generation_with_hallucinating_llm()
    print("All tests passed!")
