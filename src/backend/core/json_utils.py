"""
json_utils – Robust JSON extraction from an LLM response.
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def extract_json(text: str) -> Optional[dict]:
    """
    Try to extract a JSON object from raw text (LLM response).
    Returns the parsed dict or None.
    """
    if not text:
        return None

    cleaned = text.strip()

    # Remove markdown ```json ... ``` tags
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    else:
        # Fallback: look for a block between backticks
        code_block = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
        if code_block:
            cleaned = code_block.group(1).strip()

    # Clean up a residual "json" prefix
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()

    # Look for a JSON array or object in the text
    if not cleaned.startswith(("{", "[")):
        array_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        object_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if array_match:
            cleaned = array_match.group(0)
        elif object_match:
            cleaned = object_match.group(0)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.debug("JSON decode failed: %s | text=%s...", exc, cleaned[:200])
        return None
