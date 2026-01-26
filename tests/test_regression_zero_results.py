
"""
Regression Test: Verify 'Older Home' logic and API ergonomics.

Verifies:
1. "Older home (1940s)" does not trigger strict max_age filter.
2. /search-comps works without session_id.
3. Default sold_within_years is sensible (e.g. 2).
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app, state, _load_sample_data
from connectors.reso_mock_connector import InMemoryRESOConnector, MockRESOServer
from llm.client import MockLLMClient

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_state():
    from audit.audit_log import AuditLog
    state.audit_log = AuditLog()
    state.connector = InMemoryRESOConnector(MockRESOServer())
    _load_sample_data(state.connector)
    state.llm_client = MockLLMClient()
    # Mock default intent
    intent_json = '''{
        "subject_city": "Denver",
        "subject_year_built": 1940
    }'''
    state.llm_client._default_intent_response = intent_json
    state.llm_client.set_response("1940", intent_json)
    state.sessions = {}
    yield

def test_older_home_defaults():
    # 1. Simulate "Older home" notes
    # The MockLLM returns year_built=1940, but critically, 
    # it likely won't set sold_within_years unless explicitly told.
    # We rely on the DEFAULT value in IntentIR being safe.
    
    response = client.post("/search-comps", json={
        "intent": {
            "subject_city": "Denver",
            "subject_year_built": 1940
            # sold_within_years missing -> should default to 2
        }
    })
    
    assert response.status_code == 200
    data = response.json()
    
    # Check default behavior
    packet = data["review_packet"]
    assert packet["intent"]["sold_within_years"] == 2
    
    # In mock data, we have listings sold recently (last 90 days).
    # 2 years should catch them all.
    assert len(packet["candidates"]) > 0
    assert data["total_found"] > 0
    
def test_api_ergonomics_no_session():
    # Call /search-comps without session_id
    response = client.post("/search-comps", json={
        "intent": {"subject_city": "Denver"}
    })
    
    assert response.status_code == 200
    data = response.json()
    
    # Server should generate session_id
    assert "session_id" in data
    assert len(data["session_id"]) > 10
    assert data["review_packet"]["session_id"] == data["session_id"]
