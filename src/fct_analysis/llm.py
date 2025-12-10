"""LLM wrapper for local Ollama HTTP endpoint.

This module provides a defensive client that attempts to call a local Ollama
server but raises `ConnectionError` when unavailable. Callers should catch
ConnectionError and fall back to heuristics.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict

try:
    import requests
except Exception:  # pragma: no cover - requests may be absent in some environments
    requests = None  # type: ignore


DEFAULT_OLLAMA_URL = "http://localhost:11434"


def extract_entities_with_ollama(
    text: str,
    model: str = "qwen2.5-7b-instruct",
    ollama_url: str | None = None,
    timeout: int = 60,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> dict[str, Any] | None:
    """Call local Ollama to extract visa office and judge from case text.

    Args:
        text: Case text (title + docket entries)
        model: Ollama model name
        ollama_url: Base URL for Ollama, defaults to localhost:11434
        timeout: Request timeout in seconds
        max_retries: Number of retry attempts
        retry_delay: Delay between retries in seconds

    Returns:
        Dict with "visa_office" and/or "judge" keys, or None on error

    Raises:
        ConnectionError: When Ollama is not reachable
    """
    if not requests:
        raise ConnectionError("requests library not available")
    
    if not text or not text.strip():
        return None

    base_url = ollama_url or DEFAULT_OLLAMA_URL
    prompt = _build_extraction_prompt(text)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(
                f"{base_url}/api/generate",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            raw_output = data.get("response", "")
            return _parse_llm_output(raw_output)
        except (requests.RequestException, requests.Timeout) as e:
            if attempt == max_retries:
                raise ConnectionError(f"Failed to connect to Ollama after {max_retries + 1} attempts: {e}")
            time.sleep(retry_delay)
    return None


def _build_extraction_prompt(text: str) -> str:
    """Build a structured prompt for entity extraction."""
    return f"""Extract the following entities from this Canadian Federal Court immigration case text:

CASE TEXT:
{text}

Return a JSON object with these fields:
- visa_office: The visa office mentioned (e.g., Beijing, Ankara, New Delhi) or null
- judge: The judge name mentioned (e.g., Justice Smith) or null

Return only the JSON object, no explanation."""


def _parse_llm_output(raw_output: str) -> dict[str, Any] | None:
    """Parse the raw LLM output and extract structured entities."""
    try:
        # Try to find JSON in the output
        start = raw_output.find("{")
        end = raw_output.rfind("}") + 1
        if start != -1 and end > start:
            json_str = raw_output[start:end]
            data = json.loads(json_str)
            result = {}
            if data.get("visa_office"):
                result["visa_office"] = str(data["visa_office"]).strip()
            if data.get("judge"):
                result["judge"] = str(data["judge"]).strip()
            return result if result else None
    except (json.JSONDecodeError, Exception):
        pass
    return None