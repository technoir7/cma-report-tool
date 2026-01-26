
"""
Test UI Rendering.

Verifies:
1. Base template rendering (Disclaimer checks)
2. Review screen rendering
3. Report screen rendering
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.main import app, state, _load_sample_data
from connectors.reso_mock_connector import InMemoryRESOConnector, MockRESOServer
from llm.client import MockLLMClient
from audit.audit_log import AuditLog

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_state():
    state.audit_log = AuditLog()
    state.connector = InMemoryRESOConnector(MockRESOServer())
    _load_sample_data(state.connector)
    state.llm_client = MockLLMClient()
    # Mock default responses
    intent_json = '''{
        "subject_city": "Denver",
        "subject_state": "CO"
    }'''
    state.llm_client._default_intent_response = intent_json
    state.llm_client.set_response("Denver", intent_json)
    state.sessions = {}
    yield

def test_ui_index_renders():
    response = client.get("/ui")
    assert response.status_code == 200
    assert "CMA Compiler" in response.text
    # Check Disclaimer Footer
    assert "Informational only; not an appraisal" in response.text
    assert "Based on data from" in response.text

def test_ui_search_flow():
    # 1. Post Search -> Review Page
    response = client.post("/ui/search", data={"notes": "3 bed 2 bath in Denver 80202"})
    assert response.status_code == 200
    html = response.text
    
    # Check Review Page elements
    assert "Review Candidates" in html
    assert "Select properties to include" in html
    assert "Search Rules" in html # Sidebar
    assert "Generate Report" in html
    assert "Informational only; not an appraisal" in html # Footer
    
    # Check candidate table
    assert "Denver" in html
    assert "match" in html # Score column
    
    # Extract session_id for next step (simple heuristic parse)
    import re
    match = re.search(r'name="session_id" value="([^"]+)"', html)
    assert match
    session_id = match.group(1)
    
    # Extract listing IDs
    # For mock data we know IDs like CMA-001
    listing_id = "CMA-001"
    
    # 2. Post Generate -> Report Page
    response = client.post("/ui/generate", data={
        "session_id": session_id,
        "selected_ids": [listing_id]
    })
    
    assert response.status_code == 200
    html = response.text
    
    # Check Report Page elements
    assert "Comparative Market Analysis" in html
    assert "Start Over" in html # Nav
    assert "Print / Save PDF" in html # Action bar
    assert "Indicated Value" in html
    
    # Check Disclaimer (should be in base or wrapper)
    assert "Informational only; not an appraisal" in html
