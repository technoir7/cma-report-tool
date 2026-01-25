"""
Test hallucination guard functionality.

These tests verify that:
1. Clean output passes verification
2. Output with unauthorized numbers fails
3. Retry mechanism works correctly
4. Hard failure occurs after retry exhaustion
"""

import pytest
from decimal import Decimal
from datetime import datetime
from uuid import uuid4

from llm.report_writer import (
    HallucinationVerifier, ReportWriter, HallucinationError, generate_report
)
from llm.client import MockLLMClient
from domain.report_schema import (
    ReportJSON, SubjectProperty, AddressInfo, PropertyCharacteristics,
    CompProperty, SaleInfo, AnalyticsSection
)


class TestHallucinationVerifier:
    """Tests for HallucinationVerifier."""
    
    @pytest.fixture
    def verifier(self):
        """Create a verifier instance."""
        return HallucinationVerifier()
    
    @pytest.fixture
    def allowed_values(self):
        """Create a set of allowed values."""
        return {
            Decimal("500000"),
            Decimal("520000"),
            Decimal("275.50"),
            Decimal("1800"),
            Decimal("2000"),
            Decimal("3"),
            Decimal("2"),
            Decimal("2015"),
        }
    
    def test_extract_numbers_basic(self, verifier):
        """Test basic number extraction."""
        text = "The price is $500,000 with 1,800 sqft."
        numbers = verifier.extract_numbers(text)
        
        assert Decimal("500000") in numbers
        assert Decimal("1800") in numbers
    
    def test_extract_numbers_decimals(self, verifier):
        """Test decimal number extraction."""
        text = "Price per sqft is $275.50 with 2.5 baths."
        numbers = verifier.extract_numbers(text)
        
        assert Decimal("275.50") in numbers
        assert Decimal("2.5") in numbers
    
    def test_extract_numbers_with_dollar_sign(self, verifier):
        """Test extraction handles dollar signs."""
        text = "The value is $500,000."
        numbers = verifier.extract_numbers(text)
        
        assert Decimal("500000") in numbers
    
    def test_verify_clean_output(self, verifier, allowed_values):
        """Test that clean output passes verification."""
        text = "The property sold for $500,000 with 1,800 sqft, yielding $275.50 per sqft."
        
        is_valid, hallucinated = verifier.verify(text, allowed_values)
        
        assert is_valid is True
        assert len(hallucinated) == 0
    
    def test_verify_hallucinated_output(self, verifier, allowed_values):
        """Test that hallucinated numbers are detected."""
        # 999999 is not in allowed values
        text = "The property sold for $999,999 last year."
        
        is_valid, hallucinated = verifier.verify(text, allowed_values)
        
        assert is_valid is False
        assert Decimal("999999") in hallucinated
    
    def test_verify_multiple_hallucinations(self, verifier, allowed_values):
        """Test multiple hallucinated values are all caught."""
        text = "The price was $888,888 with 5,555 sqft."
        
        is_valid, hallucinated = verifier.verify(text, allowed_values)
        
        assert is_valid is False
        assert len(hallucinated) >= 2
        assert Decimal("888888") in hallucinated
        assert Decimal("5555") in hallucinated
    
    def test_verify_allows_common_numbers(self, verifier):
        """Test that common numbers (0-10, 100) are always allowed."""
        allowed = {Decimal("500000")}
        text = "There are 3 bedrooms and 2 bathrooms. Score is 100."
        
        is_valid, hallucinated = verifier.verify(text, allowed)
        
        # 3, 2, 100 should be in ALWAYS_ALLOWED
        assert is_valid is True
    
    def test_verify_with_tolerance(self):
        """Test that numbers within tolerance are accepted."""
        verifier = HallucinationVerifier(tolerance=0.01)  # 1% tolerance
        allowed = {Decimal("500000")}
        
        # 500050 is within 0.01% of 500000
        text = "The price is $500,050."
        
        is_valid, hallucinated = verifier.verify(text, allowed)
        
        assert is_valid is True


class TestReportWriter:
    """Tests for ReportWriter with hallucination detection."""
    
    @pytest.fixture
    def sample_report(self):
        """Create a sample ReportJSON for testing."""
        return ReportJSON(
            subject=SubjectProperty(
                address=AddressInfo(
                    street="123 Main St",
                    city="Denver",
                    state="CO",
                    zip_code="80202"
                ),
                characteristics=PropertyCharacteristics(
                    property_type="SFR",
                    bedrooms=3,
                    bathrooms=2.0,
                    living_area_sqft=1800,
                    year_built=2015
                )
            ),
            selected_comps=[
                CompProperty(
                    listing_id="COMP-001",
                    address=AddressInfo(
                        street="456 Oak Ave",
                        city="Denver",
                        state="CO",
                        zip_code="80202"
                    ),
                    characteristics=PropertyCharacteristics(
                        property_type="SFR",
                        bedrooms=3,
                        bathrooms=2.0,
                        living_area_sqft=1850
                    ),
                    sale_info=SaleInfo(
                        close_price=Decimal("520000"),
                        close_date=datetime.now()
                    ),
                    distance_miles=Decimal("0.5"),
                    similarity_score=Decimal("85"),
                    adjusted_price=Decimal("515000"),
                    adjustments=[]
                )
            ],
            analytics=AnalyticsSection(
                indicated_value=Decimal("515000"),
                value_range_low=Decimal("490000"),
                value_range_high=Decimal("540000"),
                confidence_score=Decimal("75"),
                median_price=Decimal("520000"),
                mean_price=Decimal("520000"),
                price_std_dev=Decimal("15000"),
                median_price_per_sqft=Decimal("281.08"),
                mean_price_per_sqft=Decimal("281.08"),
                median_adjusted_price=Decimal("515000"),
                mean_adjusted_price=Decimal("515000"),
                avg_days_on_market=Decimal("18"),
                total_comps_analyzed=1
            )
        )
    
    def test_generate_clean_report(self, sample_report):
        """Test that clean narrative is accepted."""
        mock_client = MockLLMClient()
        
        # Set up mock to return narrative with only allowed values
        # Note: Only use numeric values that are in the report's allowed_values
        clean_narrative = """
# Comparative Market Analysis

The subject property has 3 bedrooms and 2 bathrooms.
The indicated value is $515,000 based on 1 comparable sale.
The comparable sold for $520,000 with 1,850 sqft.
"""
        mock_client.set_response("REPORT DATA", clean_narrative)
        
        writer = ReportWriter(mock_client, max_retries=1)
        narrative = writer.generate(sample_report)
        
        assert "515,000" in narrative or "515000" in narrative.replace(",", "")
    
    def test_generate_detects_hallucination(self, sample_report):
        """Test that hallucinated narrative is detected and retried."""
        mock_client = MockLLMClient()
        call_count = [0]
        
        def mock_complete(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call returns hallucinated value
                return type('Response', (), {
                    'content': "The property is worth $999,999.",
                    'model': 'mock',
                    'prompt_tokens': 100,
                    'completion_tokens': 50,
                    'total_tokens': 150,
                    'finish_reason': 'stop'
                })()
            else:
                # Retry returns clean value
                return type('Response', (), {
                    'content': "The indicated value is $515,000.",
                    'model': 'mock',
                    'prompt_tokens': 100,
                    'completion_tokens': 50,
                    'total_tokens': 150,
                    'finish_reason': 'stop'
                })()
        
        mock_client.complete = mock_complete
        
        writer = ReportWriter(mock_client, max_retries=1)
        narrative = writer.generate(sample_report)
        
        # Should have retried and succeeded
        assert call_count[0] == 2
        assert "515,000" in narrative or "515000" in narrative.replace(",", "")
    
    def test_generate_fails_after_retries_exhausted(self, sample_report):
        """Test that persistent hallucination causes hard failure."""
        mock_client = MockLLMClient()
        
        # Always return hallucinated value
        mock_client.set_response("", "The property is worth $999,999.")
        
        writer = ReportWriter(mock_client, max_retries=1)
        
        with pytest.raises(HallucinationError) as exc_info:
            writer.generate(sample_report)
        
        assert len(exc_info.value.hallucinated_values) > 0
        assert Decimal("999999") in exc_info.value.hallucinated_values
    
    def test_correction_prompt_includes_hallucinated_values(self, sample_report):
        """Test that retry prompt mentions the hallucinated values."""
        mock_client = MockLLMClient()
        prompts_received = []
        
        original_complete = mock_client.complete
        
        def tracking_complete(*args, **kwargs):
            if 'prompt' in kwargs:
                prompts_received.append(kwargs['prompt'])
            elif args:
                prompts_received.append(args[0])
            
            # Always hallucinate to force retry
            return type('Response', (), {
                'content': "The property is worth $999,999.",
                'model': 'mock',
                'prompt_tokens': 100,
                'completion_tokens': 50,
                'total_tokens': 150,
                'finish_reason': 'stop'
            })()
        
        mock_client.complete = tracking_complete
        
        writer = ReportWriter(mock_client, max_retries=1)
        
        with pytest.raises(HallucinationError):
            writer.generate(sample_report)
        
        # Second prompt should mention the hallucinated value
        assert len(prompts_received) >= 2
        assert "999999" in prompts_received[1] or "999,999" in prompts_received[1]


class TestHallucinationErrorDetails:
    """Tests for HallucinationError exception details."""
    
    def test_error_contains_hallucinated_values(self):
        """Test that error includes hallucinated values."""
        error = HallucinationError(
            "Test error",
            hallucinated_values=[Decimal("999999"), Decimal("888888")],
            allowed_values_sample=[Decimal("500000")]
        )
        
        assert len(error.hallucinated_values) == 2
        assert Decimal("999999") in error.hallucinated_values
    
    def test_error_message_format(self):
        """Test that error message is informative."""
        error = HallucinationError(
            "Hallucination detected",
            hallucinated_values=[Decimal("999999")]
        )
        
        assert "Hallucination" in str(error)
