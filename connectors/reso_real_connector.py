"""
Real RESO Connector: Stub for production RESO Web API integration.

This module is a STUB that will be implemented when real MLS credentials
are available. It follows the same interface as other connectors.

WHY THIS IS A STUB:
- Real RESO API integration requires MLS membership and credentials
- OAuth2 authentication flow needs proper secrets management
- Production use requires compliance review and data agreements
- This allows the system to be fully tested with mock data first

HOW TO FILL LATER:
1. Implement OAuth2 token management
2. Add proper error handling for rate limits
3. Implement incremental sync for large datasets
4. Add credential rotation support
"""

from datetime import datetime
from typing import Any

from connectors.base import DataConnector, ListingRecord
from domain.policies import BackendCapability, BACKEND_CAPABILITIES
from domain.query_plan import QueryPlan


class RESOCredentialsError(Exception):
    """Raised when RESO credentials are missing or invalid."""
    pass


class RESONotImplementedError(NotImplementedError):
    """Raised when real RESO integration is attempted but not available."""
    pass


class RESORealConnector(DataConnector):
    """
    Connector for production RESO Web API.
    
    STUB IMPLEMENTATION - Not functional until credentials are provided.
    
    When implemented, this will:
    - Authenticate via OAuth2
    - Use proper token refresh
    - Handle rate limiting
    - Support incremental polling
    """
    
    def __init__(
        self,
        api_base_url: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        bearer_token: str | None = None,
    ):
        super().__init__(source_name="reso_real")
        self.api_base_url = api_base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.bearer_token = bearer_token
        
        # Validate that we have some form of credentials
        # (stub will still raise NotImplemented)
        self._has_credentials = bool(
            bearer_token or (client_id and client_secret)
        )
    
    @property
    def capability(self) -> BackendCapability:
        """Return real RESO backend capabilities."""
        return BACKEND_CAPABILITIES["reso_real"]
    
    def _execute_search(self, query_plan: QueryPlan) -> list[dict[str, Any]]:
        """
        Execute search against real RESO Web API.
        
        NOT IMPLEMENTED - Requires real credentials.
        """
        raise RESONotImplementedError(
            "Real RESO integration pending credentials. "
            "Use RESOmockConnector or CSVConnector for development. "
            "To implement: "
            "1. Obtain MLS membership and RESO certification "
            "2. Set up OAuth2 credentials "
            "3. Complete compliance review "
            "4. Implement this method with proper authentication"
        )
    
    def get_by_id(self, listing_id: str) -> ListingRecord | None:
        """
        Retrieve a single listing from real RESO API.
        
        NOT IMPLEMENTED - Requires real credentials.
        """
        raise RESONotImplementedError(
            "Real RESO integration pending credentials."
        )
    
    def health_check(self) -> bool:
        """
        Check real RESO API availability.
        
        Returns False since not implemented.
        """
        return False
    
    def _authenticate(self) -> str:
        """
        Authenticate with RESO API and get access token.
        
        STUB - Will implement OAuth2 flow when credentials available.
        
        Expected implementation:
        ```python
        response = httpx.post(
            f"{self.api_base_url}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "api",
            }
        )
        return response.json()["access_token"]
        ```
        """
        raise RESONotImplementedError("OAuth2 flow not implemented")
    
    def _refresh_token(self) -> str:
        """
        Refresh OAuth2 access token.
        
        STUB - Will implement token refresh when credentials available.
        """
        raise RESONotImplementedError("Token refresh not implemented")
