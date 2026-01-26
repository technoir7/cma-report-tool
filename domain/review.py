
"""
Review Domain: Models for human-in-the-loop review.

This module defines the data structures exchanged during the agent review
step. The ReviewPacket allows agents to:
1. See ranked candidates with explicit reasons.
2. Modify inclusion/exclusion judgments.
3. Tweak assumptions (IntentIR) and re-run.
"""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from domain.intent_ir import IntentIR
from domain.report_schema import CompProperty, AnalyticsSection


class ReviewPacket(BaseModel):
    """
    The state object for the agent review screen.
    
    Contains everything needed to make a decision:
    - What we looked for (Intent)
    - What we found (Candidates)
    - What we picked (Selected)
    - What it means (Analytics Preview)
    """
    
    session_id: str
    packet_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # The search parameters (modifiable)
    intent: IntentIR
    
    # The pool of potential comps (ranked)
    # These are fully hydrated CompProperty objects with scores/reasons
    candidates: list[CompProperty] = Field(default_factory=list)
    
    # IDs of the comps currently selected for the report
    selected_listing_ids: list[str] = Field(default_factory=list)
    
    # Live preview of the numbers (optional, computed on fly)
    analytics_preview: AnalyticsSection | None = None
    
    # Validation/System warnings
    warnings: list[str] = Field(default_factory=list)
    
    def validate_selection_limit(self, limit: int = 20):
        """Ensure selection count is within bounds."""
        if len(self.selected_listing_ids) > limit:
            raise ValueError(f"Selection exceeds limit of {limit}")
