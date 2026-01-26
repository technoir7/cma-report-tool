
"""
Test PDF Download Workflow.

Verifies:
1. Search -> Review -> Generate PDF
2. PDF Content-Type and Disposition headers
3. PDF content is not empty
"""

import pytest
from fastapi.testclient import TestClient
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

def test_pdf_download_cycle():
    # 1. Start Search to get session
    response = client.post("/ui/search", data={"notes": "3 bed 2 bath in Denver"})
    assert response.status_code == 200
    
    # Extract session_id
    import re
    match = re.search(r'name="session_id" value="([^"]+)"', response.text)
    assert match
    session_id = match.group(1)
    
    # 2. Request PDF Download
    # Note: We don't need to select ids explicitly if we just re-use the packet defaults,
    # but let's be safe and assume the packet updates the selection on download? 
    # Actually ui_download_pdf uses packet.selected_listing_ids, which defaults to top N.
    
    response = client.post("/ui/download-pdf", data={"session_id": session_id})
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in response.headers["content-disposition"]
    
    # Check content
    content = response.content
    assert len(content) > 1000  # Should be substantial
    assert content.startswith(b"%PDF")
