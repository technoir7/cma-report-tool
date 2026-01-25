"""
LLM Client: Task-aware provider switching for language models.

This module provides a protocol-based interface for LLM providers,
with support for task-specific model selection and per-task provider switching.

SUPPORTED PROVIDERS:
- Ollama (default): Local models, no API key required
- Claude: Anthropic's Claude models, requires ANTHROPIC_API_KEY
- OpenAI: GPT models, requires OPENAI_API_KEY
- Mock: For testing

TASK-BASED MODEL SELECTION:
- "notes": Notes → IntentIR JSON parsing
- "report": ReportJSON → markdown report writing

ENV VARS FOR CONFIGURATION:
- LLM_PROVIDER: "ollama" (default), "claude", "openai", "mock"
- OLLAMA_BASE_URL: default "http://localhost:11434"
- OLLAMA_MODEL: default fallback model (default "llama3.2:latest")
- LLM_NOTES_MODEL: optional override for notes task
- LLM_REPORT_MODEL: optional override for report task
- ANTHROPIC_API_KEY: required if using claude
- CLAUDE_MODEL: default Claude model (default "claude-sonnet-4-20250514")
- CLAUDE_NOTES_MODEL: optional override for notes task
- CLAUDE_REPORT_MODEL: optional override for report task
- LLM_NOTES_PROVIDER: optional per-task provider override
- LLM_REPORT_PROVIDER: optional per-task provider override

CRITICAL CONSTRAINTS:
- LLMs are ONLY used for: (a) parsing notes to IntentIR, (b) generating narrative
- LLMs NEVER access MLS data directly
- LLMs NEVER make decisions about what data to fetch
- All LLM outputs must be validated before use
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, runtime_checkable, Literal
import json
import logging
import os

logger = logging.getLogger(__name__)

# Type alias for task names
TaskType = Literal["notes", "report"]


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str | None = None


@runtime_checkable
class LLMClient(Protocol):
    """
    Protocol for LLM client implementations.
    
    Any class implementing complete() and get_model_name() can be used.
    """
    
    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        task: TaskType | None = None,
    ) -> LLMResponse:
        """
        Generate a completion from the LLM.
        
        Args:
            prompt: The user prompt
            system: Optional system prompt
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens to generate
            task: Optional task type for model selection ("notes" or "report")
            
        Returns:
            LLMResponse with content and metadata
        """
        ...
    
    def get_model_name(self, task: TaskType | None = None) -> str:
        """Return the model identifier, optionally for a specific task."""
        ...


class MockLLMClient:
    """
    Mock LLM client for testing without API calls.
    
    Returns pre-configured responses for known prompts.
    """
    
    def __init__(self):
        self.model_name = "mock-model"
        self.call_count = 0
        self.last_prompt: str | None = None
        self.last_system: str | None = None
        
        # Pre-configured responses
        self._responses: dict[str, str] = {}
        self._default_intent_response = json.dumps({
            "subject_address": "123 Main St",
            "subject_city": "Denver",
            "subject_state": "CO",
            "subject_zip": "80202",
            "subject_beds": 3,
            "subject_baths": 2.0,
            "subject_sqft": 1800,
            "subject_year_built": 2015,
            "property_type": "SFR",
            "search_radius_miles": 1.0,
            "max_age_years": 1
        })
        self._default_narrative_response = """
# Comparative Market Analysis

## Subject Property
The subject property is located at the specified address.

## Comparable Sales Analysis
Based on the provided comparable sales data, the analysis indicates market conditions.

## Value Indication
The indicated value range is based on the comparable sales analyzed.

## Limitations
This analysis is subject to the data limitations noted.
"""
    
    def set_response(self, prompt_contains: str, response: str):
        """Set a response for prompts containing the given text."""
        self._responses[prompt_contains] = response
    
    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        task: TaskType | None = None,
    ) -> LLMResponse:
        """Return mock response."""
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system = system
        
        # Check for configured responses
        for key, response in self._responses.items():
            if key in prompt:
                content = response
                break
        else:
            # Default based on task or prompt type
            if task == "notes" or "IntentIR" in (system or "") or "JSON" in prompt[:100]:
                content = self._default_intent_response
            else:
                content = self._default_narrative_response
        
        return LLMResponse(
            content=content,
            model=self.model_name,
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(content.split()),
            total_tokens=len(prompt.split()) + len(content.split()),
            finish_reason="stop"
        )
    
    def get_model_name(self, task: TaskType | None = None) -> str:
        return self.model_name


class OllamaClient:
    """
    Ollama local LLM client.
    
    Connects to a local Ollama instance for running local models.
    Uses /api/chat endpoint for proper message handling.
    
    Recommended models:
    - llama3.2:latest (2GB, fast) - good for notes parsing
    - llama3.1:latest (4.9GB) - better for report writing
    """
    
    def __init__(
        self,
        model: str | None = None,
        api_base: str | None = None,
        notes_model: str | None = None,
        report_model: str | None = None,
    ):
        self.api_base = (api_base or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        
        # Default model from env or parameter
        default_model = os.environ.get("OLLAMA_MODEL", "llama3.2:latest")
        self.model = model or default_model
        
        # Task-specific models
        self.notes_model = notes_model or os.environ.get("LLM_NOTES_MODEL", self.model)
        self.report_model = report_model or os.environ.get("LLM_REPORT_MODEL", self.model)
    
    def _get_model_for_task(self, task: TaskType | None) -> str:
        """Get the appropriate model for the given task."""
        if task == "notes":
            return self.notes_model
        elif task == "report":
            return self.report_model
        return self.model
    
    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        task: TaskType | None = None,
    ) -> LLMResponse:
        """Call Ollama API using /api/chat endpoint."""
        import httpx
        
        model = self._get_model_for_task(task)
        
        # Build messages for chat API
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        logger.debug(f"Calling Ollama {model} for task={task}")
        
        response = httpx.post(
            f"{self.api_base}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            },
            timeout=120.0
        )
        response.raise_for_status()
        data = response.json()
        
        # Extract response from message.content
        content = data.get("message", {}).get("content", "")
        
        return LLMResponse(
            content=content,
            model=model,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            finish_reason="stop" if data.get("done") else None
        )
    
    def get_model_name(self, task: TaskType | None = None) -> str:
        model = self._get_model_for_task(task)
        return f"ollama/{model}"


class ClaudeClient:
    """
    Anthropic Claude API client.
    
    Requires ANTHROPIC_API_KEY environment variable.
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        notes_model: str | None = None,
        report_model: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "Claude requires ANTHROPIC_API_KEY environment variable. "
                "Set LLM_PROVIDER=ollama to use local models without API key."
            )
        
        # Default model from env or parameter
        default_model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        self.model = model or default_model
        
        # Task-specific models
        self.notes_model = notes_model or os.environ.get("CLAUDE_NOTES_MODEL", self.model)
        self.report_model = report_model or os.environ.get("CLAUDE_REPORT_MODEL", self.model)
    
    def _get_model_for_task(self, task: TaskType | None) -> str:
        """Get the appropriate model for the given task."""
        if task == "notes":
            return self.notes_model
        elif task == "report":
            return self.report_model
        return self.model
    
    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        task: TaskType | None = None,
    ) -> LLMResponse:
        """Call Claude API."""
        import httpx
        
        model = self._get_model_for_task(task)
        
        logger.debug(f"Calling Claude {model} for task={task}")
        
        request_body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        
        if system:
            request_body["system"] = system
        
        if temperature > 0:
            request_body["temperature"] = temperature
        
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            },
            json=request_body,
            timeout=120.0
        )
        response.raise_for_status()
        data = response.json()
        
        # Extract content from Claude response
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        
        usage = data.get("usage", {})
        
        return LLMResponse(
            content=content,
            model=data.get("model", model),
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            finish_reason=data.get("stop_reason")
        )
    
    def get_model_name(self, task: TaskType | None = None) -> str:
        return self._get_model_for_task(task)


class OpenAIClient:
    """
    OpenAI API client implementation.
    
    Requires OPENAI_API_KEY environment variable or explicit key.
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4-turbo-preview",
        api_base: str | None = None
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.api_base = api_base or "https://api.openai.com/v1"
        
        if not self.api_key:
            raise ValueError("OpenAI API key required")
    
    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        task: TaskType | None = None,
    ) -> LLMResponse:
        """Call OpenAI API."""
        import httpx
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        response = httpx.post(
            f"{self.api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            },
            timeout=60.0
        )
        response.raise_for_status()
        data = response.json()
        
        choice = data["choices"][0]
        usage = data.get("usage", {})
        
        return LLMResponse(
            content=choice["message"]["content"],
            model=data["model"],
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            finish_reason=choice.get("finish_reason")
        )
    
    def get_model_name(self, task: TaskType | None = None) -> str:
        return self.model


def get_llm_client(
    provider: str | None = None,
    **kwargs
) -> LLMClient:
    """
    Factory function to get an LLM client.
    
    Args:
        provider: One of "mock", "openai", "ollama", "claude"
                  If None, uses LLM_PROVIDER env var (default: "ollama")
        **kwargs: Provider-specific arguments
        
    Returns:
        LLMClient implementation
    """
    # Get provider from env if not specified
    if provider is None:
        provider = os.environ.get("LLM_PROVIDER", "ollama").lower()
    
    providers = {
        "mock": MockLLMClient,
        "openai": OpenAIClient,
        "ollama": OllamaClient,
        "claude": ClaudeClient,
        "anthropic": ClaudeClient,  # Alias
    }
    
    if provider not in providers:
        raise ValueError(f"Unknown LLM provider: {provider}. Available: {list(providers.keys())}")
    
    logger.info(f"Initializing LLM client: {provider}")
    return providers[provider](**kwargs)


def get_client_for_task(task: TaskType) -> LLMClient:
    """
    Get an LLM client configured for a specific task.
    
    This allows per-task provider switching via LLM_NOTES_PROVIDER and LLM_REPORT_PROVIDER
    environment variables.
    
    Args:
        task: The task type ("notes" or "report")
        
    Returns:
        LLMClient configured for the task
    """
    # Check for per-task provider override
    if task == "notes":
        provider_override = os.environ.get("LLM_NOTES_PROVIDER")
    elif task == "report":
        provider_override = os.environ.get("LLM_REPORT_PROVIDER")
    else:
        provider_override = None
    
    return get_llm_client(provider=provider_override)


# Convenience exports
__all__ = [
    "LLMResponse",
    "LLMClient",
    "MockLLMClient",
    "OllamaClient",
    "ClaudeClient",
    "OpenAIClient",
    "get_llm_client",
    "get_client_for_task",
    "TaskType",
]
