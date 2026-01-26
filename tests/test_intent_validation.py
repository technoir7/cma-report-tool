"""
Test IntentIR validation and bounds enforcement.

These tests verify that:
1. Valid IntentIR objects are accepted
2. Out-of-bounds values are rejected
3. Missing required fields are rejected
4. Type constraints are enforced
"""

import pytest
from pydantic import ValidationError

from domain.intent_ir import IntentIR


class TestIntentIRValidation:
    """Tests for IntentIR model validation."""
    
    def test_valid_minimal_intent(self):
        """Test that minimal valid intent is accepted."""
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202"
        )
        
        assert intent.subject_city == "Denver"
        assert intent.subject_state == "CO"
        assert intent.search_radius_miles == 1.0  # default
        assert intent.sold_within_years == 2  # default
    
    def test_valid_full_intent(self):
        """Test that full valid intent is accepted."""
        intent = IntentIR(
            subject_address="456 Oak Ave",
            subject_city="Austin",
            subject_state="TX",
            subject_zip="78701",
            subject_beds=4,
            subject_baths=2.5,
            subject_sqft=2200,
            subject_lot_sqft=8000,
            subject_year_built=2018,
            property_type="SFR",
            search_radius_miles=2.0,
            price_range_min=400000,
            price_range_max=600000,
            sqft_tolerance_pct=0.25,
            sold_within_years=2,
            special_features=["pool", "garage"]
        )
        
        assert intent.subject_beds == 4
        assert intent.subject_baths == 2.5
        assert intent.property_type == "SFR"
        assert len(intent.special_features) == 2
    
    def test_state_code_must_be_uppercase(self):
        """Test that state code must be uppercase (pattern validation)."""
        # Lowercase should fail pattern validation
        with pytest.raises(ValidationError) as exc_info:
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="co",  # lowercase - should fail
                subject_zip="80202"
            )
        
        assert "subject_state" in str(exc_info.value)
        
        # Uppercase should pass
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",  # uppercase - should work
            subject_zip="80202"
        )
        assert intent.subject_state == "CO"
    
    def test_invalid_state_code_length(self):
        """Test that state code must be exactly 2 characters."""
        with pytest.raises(ValidationError) as exc_info:
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="Colorado",  # Too long
                subject_zip="80202"
            )
        
        assert "subject_state" in str(exc_info.value)
    
    def test_invalid_zip_format(self):
        """Test that ZIP code must match pattern."""
        with pytest.raises(ValidationError) as exc_info:
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="CO",
                subject_zip="8020"  # Too short
            )
        
        assert "subject_zip" in str(exc_info.value)
    
    def test_valid_zip_plus_four(self):
        """Test that ZIP+4 format is accepted."""
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202-1234"
        )
        
        assert intent.subject_zip == "80202-1234"
    
    def test_beds_exceeds_maximum(self):
        """Test that bedrooms > 20 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="CO",
                subject_zip="80202",
                subject_beds=25  # Exceeds max of 20
            )
        
        assert "subject_beds" in str(exc_info.value)
    
    def test_beds_below_minimum(self):
        """Test that bedrooms < 0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="CO",
                subject_zip="80202",
                subject_beds=-1  # Below min of 0
            )
        
        assert "subject_beds" in str(exc_info.value)
    
    def test_sqft_exceeds_maximum(self):
        """Test that sqft > 50000 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="CO",
                subject_zip="80202",
                subject_sqft=60000  # Exceeds max
            )
        
        assert "subject_sqft" in str(exc_info.value)
    
    def test_sqft_below_minimum(self):
        """Test that sqft < 100 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="CO",
                subject_zip="80202",
                subject_sqft=50  # Below min
            )
        
        assert "subject_sqft" in str(exc_info.value)
    
    def test_year_built_out_of_range(self):
        """Test that year_built outside 1800-2030 is rejected."""
        with pytest.raises(ValidationError):
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="CO",
                subject_zip="80202",
                subject_year_built=1700  # Too old
            )
        
        with pytest.raises(ValidationError):
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="CO",
                subject_zip="80202",
                subject_year_built=2050  # Future
            )
    
    def test_search_radius_exceeds_maximum(self):
        """Test that search_radius > 5.0 is clamped to 5.0."""
        # Values > 5.0 should be clamped to 5.0 (not rejected)
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202",
            search_radius_miles=10.0  # Exceeds max, should be clamped
        )
        
        assert intent.search_radius_miles == 5.0  # Clamped to max
    
    def test_price_range_min_exceeds_max(self):
        """Test that price_range_min > price_range_max is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="CO",
                subject_zip="80202",
                price_range_min=600000,
                price_range_max=400000  # Min > Max
            )
        
        assert "price_range_min must be <= price_range_max" in str(exc_info.value)
    
    def test_invalid_property_type(self):
        """Test that invalid property type is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="CO",
                subject_zip="80202",
                property_type="Mansion"  # Not a valid type
            )
        
        assert "property_type" in str(exc_info.value)
    
    def test_special_features_max_length(self):
        """Test that > 10 special features is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IntentIR(
                subject_address="123 Main St",
                subject_city="Denver",
                subject_state="CO",
                subject_zip="80202",
                special_features=[f"feature{i}" for i in range(15)]  # 15 features
            )
        
        assert "special_features" in str(exc_info.value)
    
    def test_get_sqft_range(self):
        """Test sqft range calculation."""
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202",
            subject_sqft=2000,
            sqft_tolerance_pct=0.2
        )
        
        min_sqft, max_sqft = intent.get_sqft_range()
        
        assert min_sqft == 1600  # 2000 * (1 - 0.2)
        assert max_sqft == 2400  # 2000 * (1 + 0.2)
    
    def test_get_sqft_range_no_sqft(self):
        """Test sqft range when subject_sqft is None."""
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202"
        )
        
        min_sqft, max_sqft = intent.get_sqft_range()
        
        assert min_sqft is None
        assert max_sqft is None
    
    def test_to_search_criteria(self):
        """Test conversion to search criteria dict."""
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202",
            subject_beds=3,
            subject_sqft=1800,
            property_type="SFR"
        )
        
        criteria = intent.to_search_criteria()
        
        assert criteria["city"] == "Denver"
        assert criteria["state"] == "CO"
        assert criteria["beds_min"] == 2  # 3 - 1
        assert criteria["beds_max"] == 4  # 3 + 1
        assert criteria["sqft_min"] == 1530  # 1800 * (1 - 0.15)
        assert criteria["sqft_max"] == 2070  # 1800 * (1 + 0.15)
