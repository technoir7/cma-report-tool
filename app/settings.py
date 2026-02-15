"""
Application settings with Pydantic Settings.

All configuration is loaded from environment variables with sensible defaults
for local development with Ollama (no API keys required).

LLM CONFIGURATION:
==================
By default, uses local Ollama with llama3.2:latest. No API key needed.

Environment Variables:
- LLM_PROVIDER: "ollama" (default), "claude", "openai", "mock"
- OLLAMA_BASE_URL: default "http://localhost:11434"
- OLLAMA_MODEL: default fallback model (default "llama3.2:latest")
- LLM_NOTES_MODEL: optional override for notes task
- LLM_REPORT_MODEL: optional override for report task
- ANTHROPIC_API_KEY: required if LLM_PROVIDER=claude
- CLAUDE_MODEL: default Claude model (default "claude-sonnet-4-20250514")
- CLAUDE_NOTES_MODEL: optional override
- CLAUDE_REPORT_MODEL: optional override
- LLM_NOTES_PROVIDER: per-task provider override
- LLM_REPORT_PROVIDER: per-task provider override

For production with Claude:
  export LLM_PROVIDER=claude
  export ANTHROPIC_API_KEY=sk-ant-...
  export CLAUDE_REPORT_MODEL=claude-sonnet-4-20250514

For mixed mode (local notes, Claude reports):
  export LLM_PROVIDER=ollama
  export LLM_REPORT_PROVIDER=claude
  export ANTHROPIC_API_KEY=sk-ant-...
"""

from enum import Enum
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    MOCK = "mock"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    CLAUDE = "claude"  # Alias for anthropic
    OLLAMA = "ollama"


class DataSource(str, Enum):
    """Supported data sources."""
    CSV = "csv"
    RESO_MOCK = "reso_mock"
    RESO_REAL = "reso_real"


class FieldTier(int, Enum):
    """
    Field access tiers for MLS data.
    
    Tier 0: Safe fields - can be sent to LLM
    Tier 1: Public remarks - can be sent to LLM with caution
    Tier 2+: Restricted - NEVER sent to LLM
    """
    SAFE = 0
    PUBLIC_REMARKS = 1
    RESTRICTED = 2
    CONFIDENTIAL = 3


# Field tier assignments following RESO Data Dictionary
FIELD_TIERS: dict[str, FieldTier] = {
    # Tier 0 - Safe fields (identifiers and public facts)
    "ListingId": FieldTier.SAFE,
    "ListPrice": FieldTier.SAFE,
    "ClosePrice": FieldTier.SAFE,
    "OriginalListPrice": FieldTier.SAFE,
    "ListingContractDate": FieldTier.SAFE,
    "CloseDate": FieldTier.SAFE,
    "DaysOnMarket": FieldTier.SAFE,
    "PropertyType": FieldTier.SAFE,
    "PropertySubType": FieldTier.SAFE,
    "BedroomsTotal": FieldTier.SAFE,
    "BathroomsTotalInteger": FieldTier.SAFE,
    "BathroomsFull": FieldTier.SAFE,
    "BathroomsHalf": FieldTier.SAFE,
    "LivingArea": FieldTier.SAFE,
    "LotSizeSquareFeet": FieldTier.SAFE,
    "LotSizeAcres": FieldTier.SAFE,
    "YearBuilt": FieldTier.SAFE,
    "StoriesTotal": FieldTier.SAFE,
    "GarageSpaces": FieldTier.SAFE,
    "PoolPrivateYN": FieldTier.SAFE,
    "City": FieldTier.SAFE,
    "StateOrProvince": FieldTier.SAFE,
    "PostalCode": FieldTier.SAFE,
    "Latitude": FieldTier.SAFE,
    "Longitude": FieldTier.SAFE,
    "StandardStatus": FieldTier.SAFE,
    
    # Tier 1 - Public remarks (may contain PII, use with caution)
    "PublicRemarks": FieldTier.PUBLIC_REMARKS,
    "SyndicationRemarks": FieldTier.PUBLIC_REMARKS,
    
    # Tier 2 - Restricted (agent/broker info)
    "ListAgentFullName": FieldTier.RESTRICTED,
    "ListAgentEmail": FieldTier.RESTRICTED,
    "ListAgentDirectPhone": FieldTier.RESTRICTED,
    "ListOfficeName": FieldTier.RESTRICTED,
    "BuyerAgentFullName": FieldTier.RESTRICTED,
    "BuyerAgentEmail": FieldTier.RESTRICTED,
    "PrivateRemarks": FieldTier.RESTRICTED,
    
    # Tier 3 - Confidential (owner info, never exposed)
    "OwnerName": FieldTier.CONFIDENTIAL,
    "OwnerPhone": FieldTier.CONFIDENTIAL,
    "OwnerEmail": FieldTier.CONFIDENTIAL,
    "TaxId": FieldTier.CONFIDENTIAL,
}


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    # Application
    app_name: str = "CMA Compiler"
    debug: bool = False
    log_level: str = "INFO"
    
    # Persistence Configuration
    redis_url: str = Field(default="redis://localhost:6379/0")
    session_ttl_seconds: int = Field(default=86400)  # 24 hours
    
    # LLM Provider Configuration
    # Default: Ollama (no API key required)
    llm_provider: LLMProvider = LLMProvider.OLLAMA
    
    # Ollama Configuration
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:latest"
    
    # Task-specific model overrides (work with any provider)
    llm_notes_model: str = ""  # Empty = use default for provider
    llm_report_model: str = ""  # Empty = use default for provider
    
    # Per-task provider overrides (e.g., Ollama for notes, Claude for reports)
    llm_notes_provider: str = ""  # Empty = use llm_provider
    llm_report_provider: str = ""  # Empty = use llm_provider
    
    # Claude Configuration
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    claude_notes_model: str = ""  # Empty = use claude_model
    claude_report_model: str = ""  # Empty = use claude_model
    
    # OpenAI Configuration (legacy support)
    openai_api_key: str = ""
    openai_model: str = "gpt-4-turbo-preview"
    
    # Generic LLM settings
    llm_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_max_tokens: int = Field(default=4096, ge=100, le=16000)
    
    # Data Source Configuration
    data_source: DataSource = DataSource.CSV
    csv_data_path: str = "data/mock_listings.csv"
    reso_mock_url: str = "http://localhost:8080"
    reso_real_url: str = ""
    reso_real_token: str = ""
    
    # Query Constraints (HARD CAPS - NON-NEGOTIABLE)
    max_candidate_results: int = Field(default=200, le=200)
    max_selected_comps: int = Field(default=20, le=20)
    default_search_radius_miles: float = Field(default=1.0, ge=0.1, le=5.0)
    max_search_radius_miles: float = Field(default=5.0, le=5.0)
    default_max_age_years: int = Field(default=1, ge=0, le=5)
    
    # Anti-Hallucination Settings
    hallucination_retry_count: int = Field(default=1, ge=0, le=3)
    numeric_tolerance: float = Field(default=0.001, ge=0.0)
    
    # Field Access
    max_llm_field_tier: FieldTier = FieldTier.PUBLIC_REMARKS
    
    def get_allowed_llm_fields(self) -> set[str]:
        """Return set of fields that can be sent to LLM."""
        return {
            field for field, tier in FIELD_TIERS.items()
            if tier.value <= self.max_llm_field_tier.value
        }


# Global settings instance
settings = Settings()
