"""LLM wrapper stub for local Ollama calls.

This is a placeholder for Phase 2. The real implementation should provide
batching, retry/backoff, and checkpointing.
"""
from __future__ import annotations

from typing import Any


def extract_visa_office(text: str) -> str | None:
    # Stub: real LLM call not implemented in scaffold
    return None


def extract_judge(text: str) -> str | None:
    return None
"""Lightweight Ollama client wrapper and prompt helpers.

This module provides a simple function `extract_entities_with_ollama(text, model)`
which calls a local Ollama API (if available) to extract structured entities.

The implementation is defensive: if Ollama is unreachable it raises a
ConnectionError so callers can fallback to heuristics.
"""
from __future__ import annotations

import json
import requests
from typing import Dict


DEFAULT_OLLAMA_URL = "http://localhost:11434"


def _build_prompt(text: str) -> str:
    return (
        "Extract the Visa Office (a short location name like 'Beijing' or 'Ankara') and the"
        " judge name (if present) from the following court case text. Respond as JSON with keys"
        " 'visa_office' and 'judge'. If a value is not present, use null. Text:\n\n" + text
    )


def extract_entities_with_ollama(text: str, model: str = "qwen2.5-7b-instruct", ollama_url: str | None = None) -> Dict[str, str | None]:
    """Call local Ollama to extract `visa_office` and `judge` from free text.

    Returns: {"visa_office": str|None, "judge": str|None}

    Raises ConnectionError if the Ollama server is unreachable.
    """
    url = ollama_url or DEFAULT_OLLAMA_URL
    payload = {
        "model": model,
        "prompt": _build_prompt(text),
        "max_tokens": 256,
    }

    try:
        resp = requests.post(f"{url}/api/completions", json=payload, timeout=10)
    except Exception as exc:
        raise ConnectionError(f"Could not connect to Ollama at {url}: {exc}")

    if resp.status_code != 200:
        raise ConnectionError(f"Ollama returned status {resp.status_code}: {resp.text}")

    # Ollama responses may vary; try to extract text response and parse JSON
    data = resp.json()
    # The response format typically contains a `completion` or `choices` with `message`/`content`.
    text_out = None
    if isinstance(data, dict):
        # common formats
        text_out = data.get("completion") or data.get("text")
        if not text_out:
            # try choices
            choices = data.get("choices") or []
            if choices and isinstance(choices, list):
                first = choices[0]
                text_out = first.get("message", {}).get("content") if isinstance(first.get("message"), dict) else first.get("text")

    if not text_out:
        # fallback to raw text
        text_out = resp.text

    # Try to parse JSON from the output
    try:
        parsed = json.loads(text_out)
        return {"visa_office": parsed.get("visa_office"), "judge": parsed.get("judge")}
    except Exception:
        # not JSON — attempt to find simple fields via heuristics
        # look for patterns like: "visa_office": "Beijing" or Visa Office: Beijing
        import re

        vo = None
        jg = None
        m = re.search(r'"?visa_office"?\s*[:=]\s*"?([A-Za-z \-]+)"?', text_out, re.I)
        if m:
            vo = m.group(1).strip()
        m2 = re.search(r'"?judge"?\s*[:=]\s*"?([A-Za-z\. \-]+)"?', text_out, re.I)
        if m2:
            jg = m2.group(1).strip()
        return {"visa_office": vo, "judge": jg}
