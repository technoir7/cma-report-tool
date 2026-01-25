"""
Notes Parser: Converts unstructured realtor notes to IntentIR.

This module uses an LLM to parse free-form realtor notes into
a structured IntentIR JSON object. The output is validated against
the IntentIR schema before being returned.

Uses task="notes" for model selection, allowing different models
for notes parsing vs report writing.

CRITICAL: The LLM must NEVER invent values. Missing information
must be represented as null in the output.
"""

import json
import logging
from pathlib import Path

from domain.intent_ir import IntentIR, IntentValidationError
from llm.client import LLMClient, LLMResponse, get_client_for_task

logger = logging.getLogger(__name__)

# Load prompt template
PROMPT_PATH = Path(__file__).parent / "prompts" / "notes_to_intent.txt"


class NotesParseError(Exception):
    """Raised when notes cannot be parsed to IntentIR."""
    
    def __init__(self, message: str, raw_output: str | None = None):
        self.message = message
        self.raw_output = raw_output
        super().__init__(message)


class NotesParser:
    """
    Parses unstructured realtor notes into IntentIR.
    
    Uses LLM for natural language understanding but validates
    all output against the IntentIR schema.
    """
    
    def __init__(self, llm_client: LLMClient | None = None):
        """
        Initialize parser.
        
        Args:
            llm_client: Optional LLM client. If None, uses get_client_for_task("notes")
        """
        self.llm = llm_client
        self._prompt_template = self._load_prompt()
    
    def _get_client(self) -> LLMClient:
        """Get or create LLM client for notes task."""
        if self.llm is None:
            self.llm = get_client_for_task("notes")
        return self.llm
    
    def _load_prompt(self) -> str:
        """Load the prompt template from file."""
        if PROMPT_PATH.exists():
            return PROMPT_PATH.read_text()
        else:
            # Inline fallback for testing
            return """Parse the following realtor notes into IntentIR JSON.
Output ONLY valid JSON, no other text.
If information is missing, use null.
Notes:
"""
    
    def parse(self, notes: str) -> IntentIR:
        """
        Parse realtor notes into IntentIR.
        
        Args:
            notes: Free-form realtor notes
            
        Returns:
            Validated IntentIR object
            
        Raises:
            NotesParseError: If parsing fails
            IntentValidationError: If validation fails
        """
        if not notes or not notes.strip():
            raise NotesParseError("Empty notes provided")
        
        # Build prompt
        prompt = f"{self._prompt_template}\n{notes}"
        
        # Call LLM with task="notes" for model selection
        try:
            client = self._get_client()
            response = client.complete(
                prompt=prompt,
                temperature=0.0,  # Deterministic output
                max_tokens=1024,
                task="notes"  # Task-based model selection
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise NotesParseError(f"LLM call failed: {e}")
        
        # Extract JSON from response
        raw_output = response.content.strip()
        json_str = self._extract_json(raw_output)
        
        if not json_str:
            raise NotesParseError(
                "No valid JSON found in LLM output",
                raw_output=raw_output
            )
        
        # Parse JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise NotesParseError(
                f"Invalid JSON in LLM output: {e}",
                raw_output=raw_output
            )
        
        # Validate against schema
        try:
            intent = IntentIR.model_validate(data)
        except Exception as e:
            raise NotesParseError(
                f"IntentIR validation failed: {e}",
                raw_output=raw_output
            )
        
        logger.info(f"Successfully parsed notes into IntentIR: {intent.subject_city}, {intent.subject_state}")
        return intent
    
    def _extract_json(self, text: str) -> str | None:
        """
        Extract JSON object from text that may contain other content.
        
        Handles cases where LLM output includes markdown code blocks
        or explanatory text.
        """
        # Try direct parse first
        text = text.strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        
        # Try to find JSON in markdown code block
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()
        
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                candidate = text[start:end].strip()
                if candidate.startswith("{"):
                    return candidate
        
        # Try to find JSON object boundaries
        start = text.find("{")
        if start == -1:
            return None
        
        # Find matching closing brace
        depth = 0
        for i, char in enumerate(text[start:], start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        
        return None


def parse_notes(notes: str, llm_client: LLMClient | None = None) -> IntentIR:
    """
    Convenience function to parse notes to IntentIR.
    
    Args:
        notes: Realtor notes text
        llm_client: Optional LLM client. If None, uses get_client_for_task("notes")
        
    Returns:
        Validated IntentIR
    """
    parser = NotesParser(llm_client)
    return parser.parse(notes)
