"""
Report Writer: Generates narrative from ReportJSON with anti-hallucination.

This module generates a narrative CMA report from structured ReportJSON.
It includes a REQUIRED hallucination verifier that ensures all numeric
values in the output are present in the source data.

Uses task="report" for model selection, allowing different models
for notes parsing vs report writing.

CRITICAL: Any numeric value not in ReportJSON.allowed_values causes
report rejection and retry. After retry exhaustion, the report FAILS HARD.
"""

import logging
import re
from decimal import Decimal
from pathlib import Path
from typing import Set

from domain.report_schema import ReportJSON
from llm.client import LLMClient, get_client_for_task

logger = logging.getLogger(__name__)

# Load prompt template
PROMPT_PATH = Path(__file__).parent / "prompts" / "report_writer.txt"


class HallucinationError(Exception):
    """
    Raised when hallucinated content is detected in LLM output.
    
    This is a HARD FAILURE - the report must not be used.
    """
    
    def __init__(
        self,
        message: str,
        hallucinated_values: list[Decimal],
        allowed_values_sample: list[Decimal] | None = None
    ):
        self.message = message
        self.hallucinated_values = hallucinated_values
        self.allowed_values_sample = allowed_values_sample
        super().__init__(message)


class ReportGenerationError(Exception):
    """Raised when report generation fails."""
    pass


class HallucinationVerifier:
    """
    Verifies LLM output contains only allowed numeric values.
    
    This is a REQUIRED component - all generated reports must pass
    through this verifier before being returned.
    """
    
    # Pattern to extract numbers from text
    # Matches integers, decimals, and numbers with commas
    NUMBER_PATTERN = re.compile(
        r'(?<![a-zA-Z])'  # Not preceded by letter
        r'[\$]?'  # Optional dollar sign
        r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)'  # Number with optional commas/decimals
        r'(?![a-zA-Z%])'  # Not followed by letter or %
    )
    
    # Numbers to always allow (common non-data numbers)
    ALWAYS_ALLOWED = {
        Decimal("0"), Decimal("1"), Decimal("2"), Decimal("3"),
        Decimal("4"), Decimal("5"), Decimal("6"), Decimal("7"),
        Decimal("8"), Decimal("9"), Decimal("10"), Decimal("100"),
        Decimal("202"), Decimal("2025"), Decimal("2024"), Decimal("2026"), # Allow years/common
    }
    
    def __init__(self, tolerance: float = 0.001):
        """
        Initialize verifier.
        
        Args:
            tolerance: Relative tolerance for numeric comparison
        """
        self.tolerance = tolerance
    
    def extract_numbers(self, text: str) -> list[Decimal]:
        """
        Extract all numeric values from text.
        
        Args:
            text: Text to extract numbers from
            
        Returns:
            List of Decimal values found
        """
        numbers = []
        for match in self.NUMBER_PATTERN.finditer(text):
            try:
                # Remove commas and parse
                num_str = match.group(1).replace(",", "")
                numbers.append(Decimal(num_str))
            except Exception:
                continue
        return numbers
    
    def verify(
        self,
        text: str,
        allowed_values: set[Decimal]
    ) -> tuple[bool, list[Decimal]]:
        """
        Verify all numbers in text are in allowed set.
        
        Args:
            text: Generated text to verify
            allowed_values: Set of allowed numeric values
            
        Returns:
            Tuple of (is_valid, list_of_hallucinated_values)
        """
        extracted = self.extract_numbers(text)
        hallucinated = []
        
        # Combine allowed with always-allowed
        full_allowed = allowed_values | self.ALWAYS_ALLOWED
        
        for num in extracted:
            if not self._is_allowed(num, full_allowed):
                hallucinated.append(num)
        
        return (len(hallucinated) == 0, hallucinated)
    
    def _is_allowed(self, value: Decimal, allowed: set[Decimal]) -> bool:
        """Check if a value is in the allowed set with tolerance."""
        # Exact match
        if value in allowed:
            return True
        
        # Check with tolerance for floating point issues
        for allowed_val in allowed:
            if allowed_val == Decimal("0"):
                if abs(value) < Decimal(str(self.tolerance)):
                    return True
            else:
                relative_diff = abs(value - allowed_val) / abs(allowed_val)
                if relative_diff < Decimal(str(self.tolerance)):
                    return True
        
        return False


class ReportWriter:
    """
    Generates narrative CMA reports from ReportJSON.
    
    Includes mandatory hallucination verification with retry.
    """
    
    def __init__(
        self,
        llm_client: LLMClient | None = None,
        max_retries: int = 1,
        tolerance: float = 0.001
    ):
        """
        Initialize report writer.
        
        Args:
            llm_client: Optional LLM client. If None, uses get_client_for_task("report")
            max_retries: Maximum retry attempts for hallucination (default 1)
            tolerance: Numeric comparison tolerance
        """
        self.llm = llm_client
        self.max_retries = max_retries
        self.verifier = HallucinationVerifier(tolerance)
        self._prompt_template = self._load_prompt()
    
    def _get_client(self) -> LLMClient:
        """Get or create LLM client for report task."""
        if self.llm is None:
            self.llm = get_client_for_task("report")
        return self.llm
    
    def _load_prompt(self) -> str:
        """Load the prompt template from file."""
        if PROMPT_PATH.exists():
            return PROMPT_PATH.read_text()
        else:
            return """Generate a CMA report narrative from the following data.
Use ONLY the values provided. Do not invent any numbers.

REPORT DATA:
"""
    
    def generate(self, report_json: ReportJSON) -> str:
        """
        Generate narrative report with hallucination verification.
        
        Args:
            report_json: Structured report data
            
        Returns:
            Generated narrative markdown
            
        Raises:
            HallucinationError: If hallucination detected after retries
            ReportGenerationError: If generation fails
        """
        # Get allowed values for verification
        allowed_values = report_json.allowed_values
        
        # Build prompt with report data
        report_context = report_json.to_llm_context()
        prompt = f"{self._prompt_template}\n{report_context}"
        
        attempt = 0
        last_hallucinated: list[Decimal] = []
        client = self._get_client()
        
        while attempt <= self.max_retries:
            try:
                # Generate narrative with task="report" for model selection
                response = client.complete(
                    prompt=prompt if attempt == 0 else self._build_correction_prompt(prompt, last_hallucinated),
                    temperature=0.0,
                    max_tokens=4096,
                    task="report"  # Task-based model selection
                )
                
                narrative = response.content.strip()
                
                # Verify no hallucination
                is_valid, hallucinated = self.verifier.verify(narrative, allowed_values)
                
                if is_valid:
                    logger.info("Report generated and verified successfully")
                    return narrative
                
                # Hallucination detected
                last_hallucinated = hallucinated
                logger.warning(
                    f"Hallucination detected on attempt {attempt + 1}: {hallucinated[:5]}..."
                )
                attempt += 1
                
            except Exception as e:
                logger.error(f"Report generation failed: {e}")
                raise ReportGenerationError(f"LLM call failed: {e}")
        
        # All retries exhausted - HARD FAILURE
        logger.error(
            f"Hallucination persisted after {self.max_retries} retries: {last_hallucinated}"
        )
        raise HallucinationError(
            f"Hallucinated values detected after {self.max_retries} retry attempts",
            hallucinated_values=last_hallucinated,
            allowed_values_sample=list(allowed_values)[:20]
        )
    
    def _build_correction_prompt(
        self,
        original_prompt: str,
        hallucinated_values: list[Decimal]
    ) -> str:
        """Build a correction prompt that explicitly warns about hallucination."""
        correction = f"""
CRITICAL CORRECTION REQUIRED:

Your previous response contained UNAUTHORIZED numeric values that do not appear in the source data:
{', '.join(str(v) for v in hallucinated_values[:10])}

You MUST:
1. Use ONLY numbers from the REPORT DATA section
2. If a value is not in the data, write "Not provided" 
3. Do NOT calculate new values
4. Do NOT estimate or round numbers

{original_prompt}
"""
        return correction


def generate_report(
    report_json: ReportJSON,
    llm_client: LLMClient | None = None,
    max_retries: int = 1
) -> str:
    """
    Convenience function to generate a verified report narrative.
    
    Args:
        report_json: Structured report data
        llm_client: Optional LLM client. If None, uses get_client_for_task("report")
        max_retries: Maximum hallucination retry attempts
        
    Returns:
        Verified narrative markdown
        
    Raises:
        HallucinationError: If hallucination persists
    """
    writer = ReportWriter(llm_client, max_retries=max_retries)
    return writer.generate(report_json)
