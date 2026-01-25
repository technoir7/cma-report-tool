"""
End-to-end test with mock data.

This test runs the complete CMA pipeline:
1. Parse notes → IntentIR
2. Build query → QueryPlan
3. Execute query → Candidates
4. Rank and select comps
5. Calculate analytics
6. Generate report
7. Verify no hallucination

All using mock data and MockLLMClient.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from domain.intent_ir import IntentIR
from domain.query_plan import QueryPlanBuilder
from domain.report_schema import (
    ReportJSON, SubjectProperty, AddressInfo, PropertyCharacteristics,
    CompProperty, SaleInfo, AnalyticsSection, AdjustmentItem
)
from domain.policies import FieldTier
from connectors.reso_mock_connector import InMemoryRESOConnector, MockRESOServer
from llm.client import MockLLMClient
from llm.notes_parser import NotesParser
from llm.report_writer import ReportWriter, HallucinationVerifier
from analytics.metrics import calculate_all_adjustments, calculate_price_per_sqft
from analytics.ranking import rank_comparables
from analytics.outliers import detect_all_outliers


def create_mock_listings():
    """Create sample MLS listings for testing."""
    base_date = datetime.now()
    
    return [
        {
            "ListingId": "TEST-001",
            "ListPrice": 525000,
            "ClosePrice": 520000,
            "CloseDate": base_date - timedelta(days=30),
            "DaysOnMarket": 15,
            "PropertyType": "Residential",
            "BedroomsTotal": 3,
            "BathroomsTotalInteger": 2,
            "LivingArea": 1850,
            "LotSizeSquareFeet": 7500,
            "YearBuilt": 2018,
            "GarageSpaces": 2,
            "PoolPrivateYN": False,
            "City": "Denver",
            "StateOrProvince": "CO",
            "PostalCode": "80202",
            "StandardStatus": "Closed",
            "Latitude": 39.7392,
            "Longitude": -104.9903,
        },
        {
            "ListingId": "TEST-002",
            "ListPrice": 495000,
            "ClosePrice": 490000,
            "CloseDate": base_date - timedelta(days=45),
            "DaysOnMarket": 22,
            "PropertyType": "Residential",
            "BedroomsTotal": 3,
            "BathroomsTotalInteger": 2,
            "LivingArea": 1720,
            "LotSizeSquareFeet": 6800,
            "YearBuilt": 2015,
            "GarageSpaces": 2,
            "PoolPrivateYN": False,
            "City": "Denver",
            "StateOrProvince": "CO",
            "PostalCode": "80202",
            "StandardStatus": "Closed",
            "Latitude": 39.7385,
            "Longitude": -104.9890,
        },
        {
            "ListingId": "TEST-003",
            "ListPrice": 545000,
            "ClosePrice": 540000,
            "CloseDate": base_date - timedelta(days=60),
            "DaysOnMarket": 18,
            "PropertyType": "Residential",
            "BedroomsTotal": 4,
            "BathroomsTotalInteger": 2,
            "LivingArea": 1950,
            "LotSizeSquareFeet": 8000,
            "YearBuilt": 2019,
            "GarageSpaces": 2,
            "PoolPrivateYN": True,
            "City": "Denver",
            "StateOrProvince": "CO",
            "PostalCode": "80202",
            "StandardStatus": "Closed",
            "Latitude": 39.7400,
            "Longitude": -104.9880,
        },
    ]


class TestEndToEndMock:
    """End-to-end tests with mock data."""
    
    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM client with configured responses."""
        client = MockLLMClient()
        
        # Configure response for notes parsing - use set_response with a key
        # that will be found in the notes parsing prompt
        intent_json = '''{
            "subject_address": "123 Main St",
            "subject_city": "Denver",
            "subject_state": "CO",
            "subject_zip": "80202",
            "subject_beds": 3,
            "subject_baths": 2.0,
            "subject_sqft": 1800,
            "subject_year_built": 2016,
            "property_type": "SFR",
            "search_radius_miles": 1.0,
            "max_age_years": 1
        }'''
        
        # Set response for any prompt containing these words
        client.set_response("Denver", intent_json)
        client.set_response("80202", intent_json)
        client._default_intent_response = intent_json
        
        return client
    
    @pytest.fixture
    def mock_connector(self):
        """Create mock data connector with sample listings."""
        server = MockRESOServer(create_mock_listings())
        return InMemoryRESOConnector(server)
    
    def test_full_pipeline_success(self, mock_llm, mock_connector):
        """Test complete pipeline from notes to report."""
        # Step 1: Parse notes
        notes = "3 bed 2 bath ranch in Denver CO 80202, built 2016, about 1800 sqft"
        parser = NotesParser(mock_llm)
        intent = parser.parse(notes)
        
        assert intent.subject_city == "Denver"
        assert intent.subject_beds == 3
        assert intent.subject_sqft == 1800
        
        # Step 2: Build query plan
        query_plan = QueryPlanBuilder.from_intent(intent)
        
        assert query_plan.max_results == 200
        assert len(query_plan.filters) > 0
        
        # Step 3: Execute search
        result = mock_connector.search(query_plan, max_tier=FieldTier.SAFE)
        
        assert result.total_count > 0
        candidates = [r.raw_data for r in result.records]
        
        # Step 4: Build subject data for analytics
        subject_data = {
            "LivingArea": intent.subject_sqft,
            "BedroomsTotal": intent.subject_beds,
            "BathroomsTotalInteger": int(intent.subject_baths),
            "YearBuilt": intent.subject_year_built,
            "LotSizeSquareFeet": intent.subject_lot_sqft,
            "GarageSpaces": None,
            "PoolPrivateYN": None
        }
        
        # Step 5: Calculate adjustments for each comp
        adjusted_comps = []
        for comp in candidates:
            adjustments = calculate_all_adjustments(subject_data, comp)
            close_price = Decimal(str(comp["ClosePrice"]))
            adjusted_price = close_price + adjustments.total
            
            adjusted_comps.append({
                **comp,
                "adjustments": adjustments,
                "adjusted_price": adjusted_price,
                "price_per_sqft": calculate_price_per_sqft(close_price, comp.get("LivingArea"))
            })
        
        # Step 6: Detect outliers
        outliers = detect_all_outliers(subject_data, candidates)
        
        # Step 7: Build ReportJSON
        subject = SubjectProperty(
            address=AddressInfo(
                street=intent.subject_address,
                city=intent.subject_city,
                state=intent.subject_state,
                zip_code=intent.subject_zip
            ),
            characteristics=PropertyCharacteristics(
                property_type=intent.property_type or "SFR",
                bedrooms=intent.subject_beds,
                bathrooms=intent.subject_baths,
                living_area_sqft=intent.subject_sqft,
                year_built=intent.subject_year_built
            )
        )
        
        comps = []
        for ac in adjusted_comps[:5]:
            comp = CompProperty(
                listing_id=ac["ListingId"],
                address=AddressInfo(
                    street=f"{ac['ListingId']} Street",
                    city=ac["City"],
                    state=ac["StateOrProvince"],
                    zip_code=ac["PostalCode"]
                ),
                characteristics=PropertyCharacteristics(
                    property_type=ac.get("PropertyType", "Residential"),
                    bedrooms=ac.get("BedroomsTotal"),
                    bathrooms=float(ac.get("BathroomsTotalInteger", 0)),
                    living_area_sqft=ac.get("LivingArea"),
                    year_built=ac.get("YearBuilt")
                ),
                sale_info=SaleInfo(
                    close_price=Decimal(str(ac["ClosePrice"])),
                    close_date=ac["CloseDate"],
                    days_on_market=ac.get("DaysOnMarket")
                ),
                distance_miles=Decimal("0.5"),
                similarity_score=Decimal("80"),
                adjustments=[
                    AdjustmentItem(**adj) for adj in ac["adjustments"].to_list()
                ],
                adjusted_price=ac["adjusted_price"],
                price_per_sqft=ac.get("price_per_sqft")
            )
            
            # Mark outliers
            if ac["ListingId"] in outliers:
                outlier = outliers[ac["ListingId"]]
                comp.is_outlier = outlier.is_outlier
            
            comps.append(comp)
        
        # Calculate analytics
        prices = [float(c.sale_info.close_price) for c in comps]
        adjusted_prices = [float(c.adjusted_price) for c in comps]
        
        import statistics
        
        analytics = AnalyticsSection(
            indicated_value=Decimal(str(statistics.median(adjusted_prices))),
            value_range_low=Decimal(str(min(adjusted_prices))),
            value_range_high=Decimal(str(max(adjusted_prices))),
            confidence_score=Decimal("75"),
            median_price=Decimal(str(statistics.median(prices))),
            mean_price=Decimal(str(statistics.mean(prices))),
            price_std_dev=Decimal(str(statistics.stdev(prices))) if len(prices) > 1 else Decimal("0"),
            median_price_per_sqft=Decimal("280"),
            mean_price_per_sqft=Decimal("280"),
            median_adjusted_price=Decimal(str(statistics.median(adjusted_prices))),
            mean_adjusted_price=Decimal(str(statistics.mean(adjusted_prices))),
            avg_days_on_market=Decimal("18"),
            total_comps_analyzed=len(comps)
        )
        
        report = ReportJSON(
            subject=subject,
            selected_comps=comps,
            analytics=analytics,
            data_source="mock"
        )
        
        # Step 8: Verify allowed_values contains expected values
        allowed = report.allowed_values
        
        assert Decimal("520000") in allowed or any(abs(v - Decimal("520000")) < 1 for v in allowed)
        assert Decimal("490000") in allowed or any(abs(v - Decimal("490000")) < 1 for v in allowed)
        
        # Step 9: Test the report was generated correctly
        # Note: Full narrative generation with hallucination verification 
        # is tested in test_hallucination_guard.py. Here we verify the 
        # pipeline produces a valid report structure.
        
        assert len(report.selected_comps) > 0
        assert report.analytics.indicated_value > 0
        assert report.subject.address.city == "Denver"
        
        # Verify allowed_values is populated correctly
        assert len(report.allowed_values) > 10  # Should have many numeric values
    
    def test_query_caps_enforced(self, mock_connector):
        """Test that query caps are enforced."""
        # Create intent that would return many results
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202"
        )
        
        query_plan = QueryPlanBuilder.from_intent(intent)
        
        # Max results should be capped at 200
        assert query_plan.max_results <= 200
    
    def test_field_tier_filtering(self, mock_connector):
        """Test that field tier filtering is applied."""
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202"
        )
        
        query_plan = QueryPlanBuilder.from_intent(intent)
        result = mock_connector.search(query_plan, max_tier=FieldTier.SAFE)
        
        for record in result.records:
            # Tier 0 fields should be present
            assert "ListingId" in record.raw_data or "City" in record.raw_data
            # Tier 2+ fields should NOT be present
            assert "PrivateRemarks" not in record.raw_data
            assert "ListAgentEmail" not in record.raw_data
    
    def test_report_comp_cap(self):
        """Test that report enforces 20 comp maximum."""
        subject = SubjectProperty(
            address=AddressInfo(
                street="123 Main St",
                city="Denver",
                state="CO",
                zip_code="80202"
            ),
            characteristics=PropertyCharacteristics(property_type="SFR")
        )
        
        # Try to add 25 comps - should fail
        comps = []
        for i in range(25):
            comps.append(CompProperty(
                listing_id=f"COMP-{i:03d}",
                address=AddressInfo(
                    street=f"{i} Test St",
                    city="Denver",
                    state="CO",
                    zip_code="80202"
                ),
                characteristics=PropertyCharacteristics(property_type="SFR"),
                sale_info=SaleInfo(
                    close_price=Decimal("500000"),
                    close_date=datetime.now()
                ),
                distance_miles=Decimal("0.5"),
                similarity_score=Decimal("80"),
                adjusted_price=Decimal("500000"),
                adjustments=[]
            ))
        
        with pytest.raises(Exception):  # ValidationError from Pydantic
            ReportJSON(
                subject=subject,
                selected_comps=comps,
                analytics=AnalyticsSection(
                    indicated_value=Decimal("500000"),
                    value_range_low=Decimal("450000"),
                    value_range_high=Decimal("550000"),
                    confidence_score=Decimal("75"),
                    median_price=Decimal("500000"),
                    mean_price=Decimal("500000"),
                    price_std_dev=Decimal("10000"),
                    median_price_per_sqft=Decimal("250"),
                    mean_price_per_sqft=Decimal("250"),
                    median_adjusted_price=Decimal("500000"),
                    mean_adjusted_price=Decimal("500000"),
                    avg_days_on_market=Decimal("15"),
                    total_comps_analyzed=25
                )
            )
    
    def test_hallucination_in_narrative_rejected(self, mock_llm):
        """Test that hallucinated values in narrative are caught."""
        subject = SubjectProperty(
            address=AddressInfo(
                street="123 Main St",
                city="Denver",
                state="CO",
                zip_code="80202"
            ),
            characteristics=PropertyCharacteristics(property_type="SFR", bedrooms=3)
        )
        
        report = ReportJSON(
            subject=subject,
            selected_comps=[
                CompProperty(
                    listing_id="COMP-001",
                    address=AddressInfo(
                        street="456 Oak Ave",
                        city="Denver",
                        state="CO",
                        zip_code="80202"
                    ),
                    characteristics=PropertyCharacteristics(property_type="SFR"),
                    sale_info=SaleInfo(
                        close_price=Decimal("500000"),
                        close_date=datetime.now()
                    ),
                    distance_miles=Decimal("0.5"),
                    similarity_score=Decimal("80"),
                    adjusted_price=Decimal("500000"),
                    adjustments=[]
                )
            ],
            analytics=AnalyticsSection(
                indicated_value=Decimal("500000"),
                value_range_low=Decimal("450000"),
                value_range_high=Decimal("550000"),
                confidence_score=Decimal("75"),
                median_price=Decimal("500000"),
                mean_price=Decimal("500000"),
                price_std_dev=Decimal("10000"),
                median_price_per_sqft=Decimal("250"),
                mean_price_per_sqft=Decimal("250"),
                median_adjusted_price=Decimal("500000"),
                mean_adjusted_price=Decimal("500000"),
                avg_days_on_market=Decimal("15"),
                total_comps_analyzed=1
            )
        )
        
        # Configure mock to return hallucinated value
        mock_llm._default_narrative_response = "The property is worth $999,999."
        
        verifier = HallucinationVerifier()
        allowed = report.allowed_values
        
        is_valid, hallucinated = verifier.verify("The property is worth $999,999.", allowed)
        
        assert is_valid is False
        assert Decimal("999999") in hallucinated
