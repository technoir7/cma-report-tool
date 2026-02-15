"""
Application Version Constants.

These versions are logged with every run_id to ensure
reproducibility and traceability.
"""

from enum import Enum


class AppVersion(str, Enum):
    """Component versions."""
    
    # Core Rules (Ranking/Filtering logic)
    RULES = "1.0.0"
    
    # LLM Prompts
    PROMPTS = "1.0.0"
    
    # Connectors (Adapter logic)
    CONNECTORS = "1.0.0"
    
    # Analytics (Math/Adjustment rules)
    ANALYTICS = "1.0.0"
