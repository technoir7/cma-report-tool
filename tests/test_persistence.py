
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from app.persistence import RedisSessionStore, MemorySessionStore

# ============================================================================
# MemoryStore Tests
# ============================================================================

@pytest.mark.asyncio
async def test_memory_store_operations():
    store = MemorySessionStore()
    session_id = "test-session"
    data = {"foo": "bar", "num": 123}
    
    # Test Save
    await store.save(session_id, data)
    
    # Test Get
    retrieved = await store.get(session_id)
    assert retrieved == data
    
    # Test Update
    data["foo"] = "baz"
    await store.save(session_id, data)
    retrieved = await store.get(session_id)
    assert retrieved["foo"] == "baz"
    
    # Test Delete
    await store.delete(session_id)
    retrieved = await store.get(session_id)
    assert retrieved is None

# ============================================================================
# RedisStore Tests (Mocked)
# ============================================================================

@pytest.mark.asyncio
async def test_redis_store_save():
    mock_redis = AsyncMock()
    
    # We patch BOTH redis.asyncio.from_url (if imported) AND app.persistence.redis (the module variable)
    # Because app.persistence.RedisSessionStore.__init__ checks `if redis is None`.
    
    with patch("app.persistence.redis", mock_redis), \
         patch("app.persistence.redis.from_url", return_value=mock_redis):
         
        store = RedisSessionStore("redis://localhost")
        
        session_id = "test-redis"
        data = {"key": "val"}
        
        await store.save(session_id, data, ttl=3600)
        
        mock_redis.set.assert_called_once_with(
            f"session:{session_id}",
            json.dumps(data),
            ex=3600
        )

@pytest.mark.asyncio
async def test_redis_store_get_hit():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps({"key": "val"})
    
    with patch("app.persistence.redis", mock_redis), \
         patch("app.persistence.redis.from_url", return_value=mock_redis):
        store = RedisSessionStore("redis://localhost")
        
        data = await store.get("test-redis")
        assert data == {"key": "val"}
        
        mock_redis.get.assert_called_once_with("session:test-redis")

@pytest.mark.asyncio
async def test_redis_store_get_miss():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    
    with patch("app.persistence.redis", mock_redis), \
         patch("app.persistence.redis.from_url", return_value=mock_redis):
        store = RedisSessionStore("redis://localhost")
        
        data = await store.get("test-redis")
        assert data is None

@pytest.mark.asyncio
async def test_redis_store_connection_error_handling():
    # Simulate initialization success but operation failure
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("Redis down")
    
    with patch("app.persistence.redis", mock_redis), \
         patch("app.persistence.redis.from_url", return_value=mock_redis):
        store = RedisSessionStore("redis://localhost")
        
        # Should return None and log error, not raise
        data = await store.get("test-redis")
        assert data is None

# ============================================================================
# Main App Integration Test (Mocked Store)
# ============================================================================

from fastapi.testclient import TestClient
from app.main import app, state

client = TestClient(app)

@pytest.mark.asyncio
async def test_app_uses_session_store():
    # Mock the session store on the app state
    mock_store = AsyncMock()
    # Mock get to return empty or None initially
    mock_store.get.return_value = None 
    
    # Patch the state's session_store
    with patch.object(state, "session_store", mock_store):
        # We need to simulate a request that uses session
        # But most endpoints generate a new session if not provided
        # Let's try /parse-notes
        
        payload = {"notes": "Looking for a house in Denver"}
        response = client.post("/parse-notes", json=payload)
        
        # It should save the new session
        assert response.status_code == 200
        assert mock_store.save.called
        
        # Get session ID from response
        session_id = response.json()["session_id"]
        
        # Verify save called with specific format
        call_args = mock_store.save.call_args
        assert call_args[0][0] == session_id # First arg is session_id
        assert "intent" in call_args[0][1] # Second arg is data dict

@pytest.mark.asyncio
async def test_app_retrieves_session():
    # Mock the session store
    mock_store = AsyncMock()
    
    # Setup existing session
    session_id = "existing-session"
    mock_intent = {
        "subject_city": "Denver",
        "subject_state": "CO",
        "subject_beds": 3,
        "subject_baths": 2
    }
    
    # Mock get to return the session data
    mock_store.get.return_value = {"intent": mock_intent}
    
    with patch.object(state, "session_store", mock_store):
        # Call search-comps with existing session_id
        payload = {"session_id": session_id}
        
        # We also need to mock _execute_search_flow or the connector/ranking
        # because the endpoint will try to run the search.
        # It's easier to mock _execute_search_flow.
        
        with patch("app.main._execute_search_flow") as mock_search:
            # Mock return of search flow
            mock_packet = MagicMock()
            mock_packet.model_dump.return_value = {
                "candidates": [], 
                "session_id": session_id,
                "intent": mock_intent
            }
            mock_packet.candidates = []
            mock_search.return_value = mock_packet
            
            response = client.post("/search-comps", json=payload)
            
            assert response.status_code == 200
            
            # Verify it tried to get the session
            mock_store.get.assert_called_with(session_id)
            
            # Verify it updated the session with results
            assert mock_store.save.call_count >= 1

