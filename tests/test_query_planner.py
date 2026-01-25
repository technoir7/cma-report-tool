"""
Test QueryPlanner bounds and cap enforcement.

These tests verify that:
1. Candidate cap is enforced (max 200)
2. Selected comp cap is enforced (max 20)
3. Field tier filtering works correctly
4. OData query generation is correct
"""

import pytest
from datetime import date
from pydantic import ValidationError

from domain.query_plan import (
    QueryPlan, QueryPlanBuilder, FilterCondition, FilterOperator,
    SortCriterion, SortDirection
)
from domain.intent_ir import IntentIR
from domain.policies import validate_query_bounds, MAX_CANDIDATE_RESULTS, MAX_SELECTED_COMPS


class TestQueryPlanValidation:
    """Tests for QueryPlan validation."""
    
    def test_max_results_cap(self):
        """Test that max_results is capped at 200."""
        # Valid at cap
        plan = QueryPlan(max_results=200)
        assert plan.max_results == 200
        
        # Exceeds cap - should raise
        with pytest.raises(ValidationError) as exc_info:
            QueryPlan(max_results=201)
        
        assert "max_results" in str(exc_info.value)
    
    def test_default_max_results(self):
        """Test that default max_results is 200."""
        plan = QueryPlan()
        assert plan.max_results == 200
    
    def test_filter_to_odata(self):
        """Test FilterCondition OData conversion."""
        # Equality
        f1 = FilterCondition(field="City", operator=FilterOperator.EQ, value="Denver")
        assert f1.to_odata() == "City eq 'Denver'"
        
        # Greater than
        f2 = FilterCondition(field="BedroomsTotal", operator=FilterOperator.GE, value=3)
        assert f2.to_odata() == "BedroomsTotal ge 3"
        
        # Less than
        f3 = FilterCondition(field="ClosePrice", operator=FilterOperator.LE, value=500000)
        assert f3.to_odata() == "ClosePrice le 500000"
        
        # Contains
        f4 = FilterCondition(field="City", operator=FilterOperator.CONTAINS, value="Den")
        assert f4.to_odata() == "contains(City, 'Den')"
    
    def test_filter_escapes_quotes(self):
        """Test that single quotes in values are escaped."""
        f = FilterCondition(field="City", operator=FilterOperator.EQ, value="O'Brien")
        assert f.to_odata() == "City eq 'O''Brien'"
    
    def test_sort_to_odata(self):
        """Test SortCriterion OData conversion."""
        s1 = SortCriterion(field="CloseDate", direction=SortDirection.DESC)
        assert s1.to_odata() == "CloseDate desc"
        
        s2 = SortCriterion(field="ClosePrice", direction=SortDirection.ASC)
        assert s2.to_odata() == "ClosePrice asc"
    
    def test_query_plan_to_odata_params(self):
        """Test full QueryPlan to OData parameter conversion."""
        plan = QueryPlan(
            select_fields=["ListingId", "ClosePrice", "City"],
            filters=[
                FilterCondition(field="City", operator=FilterOperator.EQ, value="Denver"),
                FilterCondition(field="BedroomsTotal", operator=FilterOperator.GE, value=2)
            ],
            order_by=[SortCriterion(field="CloseDate", direction=SortDirection.DESC)],
            max_results=50
        )
        
        params = plan.to_odata_params()
        
        assert params["$select"] == "ListingId,ClosePrice,City"
        assert params["$filter"] == "City eq 'Denver' and BedroomsTotal ge 2"
        assert params["$orderby"] == "CloseDate desc"
        assert params["$top"] == "50"
    
    def test_add_filter(self):
        """Test adding filters to QueryPlan."""
        plan = QueryPlan()
        
        new_plan = plan.add_filter("City", FilterOperator.EQ, "Denver")
        
        # Original unchanged
        assert len(plan.filters) == 0
        # New plan has filter
        assert len(new_plan.filters) == 1
        assert new_plan.filters[0].field == "City"
    
    def test_max_filters_limit(self):
        """Test that max 20 filters is enforced."""
        plan = QueryPlan(
            filters=[
                FilterCondition(field=f"Field{i}", operator=FilterOperator.EQ, value=i)
                for i in range(20)
            ]
        )
        
        # Adding 21st filter should raise
        with pytest.raises(ValueError) as exc_info:
            plan.add_filter("Field20", FilterOperator.EQ, "value")
        
        assert "Maximum 20 filter conditions" in str(exc_info.value)


class TestQueryPlanBuilder:
    """Tests for QueryPlanBuilder from IntentIR."""
    
    def test_build_from_minimal_intent(self):
        """Test building QueryPlan from minimal intent."""
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202"
        )
        
        plan = QueryPlanBuilder.from_intent(intent)
        
        # Check essential filters
        filter_fields = [f.field for f in plan.filters]
        assert "City" in filter_fields
        assert "StateOrProvince" in filter_fields
        assert "StandardStatus" in filter_fields
        
        # Check max_results is capped
        assert plan.max_results == 200
        
        # Check intent hash is set
        assert plan.intent_hash is not None
    
    def test_build_includes_bedroom_filters(self):
        """Test that bedroom filters are added when beds specified."""
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202",
            subject_beds=3
        )
        
        plan = QueryPlanBuilder.from_intent(intent)
        
        # Should have bedroom range filters
        bed_filters = [f for f in plan.filters if f.field == "BedroomsTotal"]
        assert len(bed_filters) == 2  # GE and LE
        
        # Check values
        ge_filter = [f for f in bed_filters if f.operator == FilterOperator.GE][0]
        le_filter = [f for f in bed_filters if f.operator == FilterOperator.LE][0]
        assert ge_filter.value == 2  # 3 - 1
        assert le_filter.value == 4  # 3 + 1
    
    def test_build_includes_sqft_filters(self):
        """Test that sqft filters are added when sqft specified."""
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202",
            subject_sqft=2000,
            sqft_tolerance_pct=0.2
        )
        
        plan = QueryPlanBuilder.from_intent(intent)
        
        sqft_filters = [f for f in plan.filters if f.field == "LivingArea"]
        assert len(sqft_filters) == 2
        
        ge_filter = [f for f in sqft_filters if f.operator == FilterOperator.GE][0]
        le_filter = [f for f in sqft_filters if f.operator == FilterOperator.LE][0]
        assert ge_filter.value == 1600  # 2000 * 0.8
        assert le_filter.value == 2400  # 2000 * 1.2
    
    def test_build_default_select_fields(self):
        """Test that default select fields are included."""
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202"
        )
        
        plan = QueryPlanBuilder.from_intent(intent)
        
        # Check essential fields are selected
        assert "ListingId" in plan.select_fields
        assert "ClosePrice" in plan.select_fields
        assert "BedroomsTotal" in plan.select_fields
        assert "LivingArea" in plan.select_fields
    
    def test_build_includes_public_remarks(self):
        """Test that PublicRemarks is included when requested."""
        intent = IntentIR(
            subject_address="123 Main St",
            subject_city="Denver",
            subject_state="CO",
            subject_zip="80202"
        )
        
        plan = QueryPlanBuilder.from_intent(intent, include_public_remarks=True)
        
        assert "PublicRemarks" in plan.select_fields


class TestQueryBoundsValidation:
    """Tests for query bounds validation function."""
    
    def test_valid_bounds(self):
        """Test that valid bounds pass."""
        violations = validate_query_bounds(
            max_results=100,
            radius_miles=2.0,
            filter_count=5,
            select_count=10
        )
        
        assert len(violations) == 0
    
    def test_max_results_violation(self):
        """Test that exceeding max_results is caught."""
        violations = validate_query_bounds(max_results=300)
        
        assert len(violations) == 1
        assert "max_results" in violations[0]
        assert "300" in violations[0]
    
    def test_radius_violation(self):
        """Test that exceeding radius limit is caught."""
        violations = validate_query_bounds(
            max_results=100,
            radius_miles=10.0
        )
        
        assert len(violations) == 1
        assert "radius_miles" in violations[0]
    
    def test_filter_count_violation(self):
        """Test that exceeding filter count is caught."""
        violations = validate_query_bounds(
            max_results=100,
            filter_count=25
        )
        
        assert len(violations) == 1
        assert "filter_count" in violations[0]
    
    def test_multiple_violations(self):
        """Test that all violations are reported."""
        violations = validate_query_bounds(
            max_results=300,
            radius_miles=10.0,
            filter_count=25,
            select_count=100
        )
        
        assert len(violations) == 4


class TestHardCaps:
    """Tests for hard cap constants."""
    
    def test_candidate_cap_value(self):
        """Verify MAX_CANDIDATE_RESULTS is 200."""
        assert MAX_CANDIDATE_RESULTS == 200
    
    def test_selected_comp_cap_value(self):
        """Verify MAX_SELECTED_COMPS is 20."""
        assert MAX_SELECTED_COMPS == 20
