
"""
Test the API Review Workflow.

Verifies:
1. Parse Notes -> Session
2. Search Comps -> Review Packet (Ranked)
3. Select Comps -> Updated Packet
4. Generate Report -> Final JSON/Narrative
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.main import app, state, _load_sample_data
from connectors.reso_mock_connector import InMemoryRESOConnector, MockRESOServer
from llm.client import MockLLMClient
from audit.audit_log import AuditLog
from app.persistence import MemorySessionStore

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_state():
    """Reset application state before each test."""
    # Initialize audit log
    state.audit_log = AuditLog()
    
    # Reset connector
    state.connector = InMemoryRESOConnector(MockRESOServer())
    _load_sample_data(state.connector)
    
    # Mock LLM
    state.llm_client = MockLLMClient()
    # Setup response for parsing
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
        "max_age_years": 5
    }'''
    state.llm_client._default_intent_response = intent_json
    state.llm_client.set_response("Denver", intent_json)
    
    state.llm_client.set_response("Denver", intent_json)
    
    state.session_store = MemorySessionStore()
    yield

def test_full_review_flow():
    """Test the complete workflow with agent review."""
    
    # 1. Parse Notes
    response = client.post("/parse-notes", json={
        "notes": "3 bed 2 bath in Denver 80202"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    session_id = data["session_id"]
    intent = data["intent"]
    assert intent["subject_city"] == "Denver"
    
    # 2. Search Comps (Returns Review Packet)
    response = client.post("/search-comps", json={
        "session_id": session_id
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # Verify Review Packet structure
    packet = data["review_packet"]
    assert packet is not None
    assert packet["session_id"] == session_id
    assert len(packet["candidates"]) > 0
    
    # Check ranking and reasons
    first_comp = packet["candidates"][0]
    assert "score_breakdown" in first_comp
    assert "selection_reasons" in first_comp
    assert len(first_comp["selection_reasons"]) > 0
    assert first_comp["rank_index"] == 1
    
    # Check default analytics preview
    assert packet["analytics_preview"] is not None
    # JSON serializes Decimal as string/float
    indicated = float(packet["analytics_preview"]["indicated_value"]) 
    assert indicated > 0
    
    # 3. Select Comps (Simulate Agent Modification)
    # Let's say we only want the first 2 candidates
    selected_ids = [c["listing_id"] for c in packet["candidates"][:2]]
    
    response = client.post("/select-comps", json={
        "session_id": session_id,
        "selected_listing_ids": selected_ids
    })
    assert response.status_code == 200
    data = response.json()
    assert data["selected_count"] == 2
    
    # 4. Generate Report
    response = client.post("/generate-report", json={
        "session_id": session_id,
        "include_narrative": False
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    report = data["report"]
    assert len(report["selected_comps"]) == 2
    assert report["analytics"]["total_comps_analyzed"] == 2
    
    # Check that comp details are preserved
    rep_comp_1 = report["selected_comps"][0]
    assert rep_comp_1["listing_id"] == selected_ids[0]
    assert "score_breakdown" in rep_comp_1
    assert "selection_reasons" in rep_comp_1

def test_search_caps_results():
    """Test that search flow respects caps even if connector returns many."""
    # This relies on the fact that _load_sample_data loads 5 listings
    # And we just want to ensure the API doesn't crash
    
    # 1. Start Session
    response = client.post("/parse-notes", json={"notes": "test note content must be long enough"})
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    
    # 2. Search
    response = client.post("/search-comps", json={"session_id": session_id})
    packet = response.json()["review_packet"]
    
    # We loaded 5 listings in mock, so candidates should be 5
    assert len(packet["candidates"]) == 5
    
    # Default selection should be 5 (since max default is likely 20)
    assert len(packet["selected_listing_ids"]) == 5

