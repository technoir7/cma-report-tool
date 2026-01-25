"""
RESO Mock Connector: Connects to a RESO Web API reference server.

This connector translates QueryPlan to OData queries and fetches
data from a mock RESO Web API server for development and testing.

For MVP, this connects to the RESO reference implementation or
a simple mock server that returns static data.
"""

from datetime import datetime, date
from typing import Any


def _normalize_for_comparison(val1: Any, val2: Any) -> tuple[Any, Any]:
    """Normalize values for comparison, handling date/datetime mismatch."""
    # Handle datetime vs date comparison
    if isinstance(val1, datetime) and isinstance(val2, date) and not isinstance(val2, datetime):
        val1 = val1.date()
    elif isinstance(val2, datetime) and isinstance(val1, date) and not isinstance(val1, datetime):
        val2 = val2.date()
    return val1, val2

import httpx

from connectors.base import DataConnector, ListingRecord
from domain.policies import BackendCapability, BACKEND_CAPABILITIES
from domain.query_plan import QueryPlan


class RESOConnectionError(Exception):
    """Raised when connection to RESO server fails."""
    pass


class RESOQueryError(Exception):
    """Raised when RESO query execution fails."""
    pass


class RESOmockConnector(DataConnector):
    """
    Connector for RESO Web API mock/reference server.
    
    Translates neutral QueryPlan to OData $filter, $select, $orderby, $top
    parameters and executes against a RESO-compliant endpoint.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: float = 30.0
    ):
        super().__init__(source_name="reso_mock")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
    
    @property
    def capability(self) -> BackendCapability:
        """Return RESO mock backend capabilities."""
        return BACKEND_CAPABILITIES["reso_mock"]
    
    def _execute_search(self, query_plan: QueryPlan) -> list[dict[str, Any]]:
        """
        Execute search against RESO mock server.
        
        Translates QueryPlan to OData query and fetches results.
        """
        # Build OData parameters
        params = query_plan.to_odata_params()
        
        # RESO Property resource endpoint
        endpoint = f"{self.base_url}/Property"
        
        try:
            response = self._client.get(endpoint, params=params)
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise RESOConnectionError(f"Failed to connect to RESO server: {e}")
        except httpx.HTTPStatusError as e:
            raise RESOQueryError(f"RESO query failed with status {e.response.status_code}: {e}")
        except httpx.TimeoutException as e:
            raise RESOConnectionError(f"RESO request timed out: {e}")
        
        # Parse OData response
        data = response.json()
        
        # OData responses have "value" array
        if isinstance(data, dict) and "value" in data:
            return data["value"]
        elif isinstance(data, list):
            return data
        else:
            return []
    
    def get_by_id(self, listing_id: str) -> ListingRecord | None:
        """Retrieve a single listing by ListingId."""
        endpoint = f"{self.base_url}/Property('{listing_id}')"
        
        try:
            response = self._client.get(endpoint)
            if response.status_code == 404:
                return None
            response.raise_for_status()
        except httpx.HTTPStatusError:
            return None
        except httpx.ConnectError:
            raise RESOConnectionError(f"Failed to connect to RESO server")
        
        data = response.json()
        return ListingRecord(
            raw_data=data,
            source=self.source_name,
            retrieved_at=datetime.utcnow()
        )
    
    def health_check(self) -> bool:
        """Check if RESO mock server is available."""
        try:
            # Try to hit the metadata endpoint
            response = self._client.get(
                f"{self.base_url}/$metadata",
                timeout=5.0
            )
            return response.status_code in (200, 404)  # 404 is ok if no metadata
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
    
    def close(self):
        """Close the HTTP client."""
        self._client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


class MockRESOServer:
    """
    In-memory mock RESO server for testing without external dependencies.
    
    This provides a simple implementation that can be used when the
    actual RESO reference server is not available.
    """
    
    def __init__(self, listings: list[dict[str, Any]] | None = None):
        self.listings = listings or []
    
    def add_listing(self, listing: dict[str, Any]):
        """Add a listing to the mock server."""
        self.listings.append(listing)
    
    def search(self, query_plan: QueryPlan) -> list[dict[str, Any]]:
        """
        Execute a search against the in-memory listings.
        
        This is a simplified implementation that handles basic filtering.
        """
        results = self.listings.copy()
        
        # Apply filters
        for f in query_plan.filters:
            field = f.field
            value = f.value
            op = f.operator.value
            
            filtered = []
            for listing in results:
                listing_value = listing.get(field)
                if listing_value is None:
                    continue
                
                # Normalize values for comparison (handles datetime vs date)
                compare_listing, compare_value = _normalize_for_comparison(listing_value, value)
                
                if op == "eq" and compare_listing == compare_value:
                    filtered.append(listing)
                elif op == "ne" and compare_listing != compare_value:
                    filtered.append(listing)
                elif op == "gt":
                    try:
                        if compare_listing > compare_value:
                            filtered.append(listing)
                    except TypeError:
                        pass  # Skip incompatible comparisons
                elif op == "ge":
                    try:
                        if compare_listing >= compare_value:
                            filtered.append(listing)
                    except TypeError:
                        pass
                elif op == "lt":
                    try:
                        if compare_listing < compare_value:
                            filtered.append(listing)
                    except TypeError:
                        pass
                elif op == "le":
                    try:
                        if compare_listing <= compare_value:
                            filtered.append(listing)
                    except TypeError:
                        pass
                elif op == "contains" and str(compare_value).lower() in str(compare_listing).lower():
                    filtered.append(listing)
            
            results = filtered
        
        # Apply ordering
        for order in reversed(query_plan.order_by):
            reverse = order.direction.value == "desc"
            results.sort(
                key=lambda x: x.get(order.field, 0) or 0,
                reverse=reverse
            )
        
        # Apply limit
        return results[:query_plan.max_results]
    
    def get_by_id(self, listing_id: str) -> dict[str, Any] | None:
        """Get a listing by ID."""
        for listing in self.listings:
            if listing.get("ListingId") == listing_id:
                return listing
        return None


class InMemoryRESOConnector(DataConnector):
    """
    Connector that uses MockRESOServer for fully offline testing.
    """
    
    def __init__(self, mock_server: MockRESOServer | None = None):
        super().__init__(source_name="reso_mock_memory")
        self._server = mock_server or MockRESOServer()
    
    @property
    def capability(self) -> BackendCapability:
        return BACKEND_CAPABILITIES["reso_mock"]
    
    def _execute_search(self, query_plan: QueryPlan) -> list[dict[str, Any]]:
        return self._server.search(query_plan)
    
    def get_by_id(self, listing_id: str) -> ListingRecord | None:
        data = self._server.get_by_id(listing_id)
        if data is None:
            return None
        return ListingRecord(
            raw_data=data,
            source=self.source_name,
            retrieved_at=datetime.utcnow()
        )
    
    def health_check(self) -> bool:
        return True
    
    def load_listings(self, listings: list[dict[str, Any]]):
        """Load listings into the mock server."""
        for listing in listings:
            self._server.add_listing(listing)
