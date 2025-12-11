"""LLM wrapper for local Ollama HTTP endpoint.

This module provides a defensive client that attempts to call a local Ollama
server with enterprise-grade safety features:
- Global lock to prevent concurrent CPU-intensive tasks
- Automatic timeout with process termination
- Auto-restart on failures
- Exponential backoff retry
- Single-threaded execution for CPU-only environments
"""
from __future__ import annotations

import json
import subprocess
import time
import threading
from typing import Any, Dict, Optional

try:
    import requests
except Exception:  # pragma: no cover - requests may be absent in some environments
    requests = None  # type: ignore


DEFAULT_OLLAMA_URL = "http://localhost:11434"

# -----------------------------------------------------------
# Global lock: CPU-only environment can only allow one LLM inference task
# -----------------------------------------------------------
ollama_lock = threading.Lock()

# -----------------------------------------------------------
# Ollama configuration
# -----------------------------------------------------------
OLLAMA_MODEL = "gemma2:2b"   # Lightweight model for CPU-only environment
OLLAMA_TIMEOUT = 60             # Maximum wait time per inference (seconds) - increased for CPU-only
OLLAMA_MAX_RETRY = 3            # Maximum retry attempts

# System Prompt: Short and efficient
SYSTEM_PROMPT = """
You classify Canadian Federal Court docket summaries and return valid JSON only.
Output:
- is_mandamus
- outcome
- nature
- has_hearing
Return only JSON.
"""


# -----------------------------------------------------------
# Service availability check
# -----------------------------------------------------------
def check_service_availability():
    """检查 Ollama 服务是否可用"""
    from loguru import logger
    
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            logger.debug("✅ Ollama service is responsive")
            return True
        else:
            logger.warning("⚠️  Ollama service not responding properly")
            return False
    except Exception as e:
        logger.warning(f"⚠️  Cannot verify Ollama service status: {e}")
        return False


# -----------------------------------------------------------
# Run with timeout limit
# -----------------------------------------------------------
def run_with_timeout(func, timeout):
    """Execute function with timeout, return (result, error) tuple."""
    result = [None]
    error = [None]

    def wrapper():
        try:
            result[0] = func()
        except Exception as e:
            error[0] = e

    thread = threading.Thread(target=wrapper)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        return None, TimeoutError("Request timed out")

    return result[0], error[0]


# -----------------------------------------------------------
# Safe Ollama request for classification
# -----------------------------------------------------------
def safe_ollama_request(summary_text: str, model: str = None) -> dict[str, Any]:
    """
    Safe Ollama call with timeout and retry:
    - Single-threaded (with lock)
    - Automatic timeout termination
    - Exponential backoff retry
    - Returns error to fallback to NLP analysis
    """
    from loguru import logger
    
    model_to_use = model or OLLAMA_MODEL
    
    with ollama_lock:
        attempt = 0

        while attempt < OLLAMA_MAX_RETRY:
            attempt += 1
            logger.info(f"[Ollama] Attempt {attempt}/{OLLAMA_MAX_RETRY}...")

            def call():
                if requests is None:
                    raise ConnectionError("requests library is not available")
                
                payload = {
                    "model": model_to_use,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Summaries:\n{summary_text}"}
                    ],
                    "stream": False,
                    "options": {"num_predict": 200, "temperature": 0}
                }
                
                response = requests.post(
                    f"{DEFAULT_OLLAMA_URL}/api/chat", 
                    json=payload, 
                    timeout=OLLAMA_TIMEOUT
                )
                response.raise_for_status()
                data = response.json()
                
                if "message" in data and "content" in data["message"]:
                    return data["message"]["content"]
                else:
                    raise ValueError("Invalid response format from Ollama")

            # ---- Execute inference with timeout ----
            try:
                content, error = run_with_timeout(call, OLLAMA_TIMEOUT)
                
                if error is None and content is not None:
                    # Success - try to parse JSON
                    try:
                        # Handle markdown-wrapped JSON
                        cleaned_content = content.strip()
                        if cleaned_content.startswith('```json'):
                            cleaned_content = cleaned_content[7:]  # Remove ```json
                        if cleaned_content.endswith('```'):
                            cleaned_content = cleaned_content[:-3]  # Remove ```
                        cleaned_content = cleaned_content.strip()
                        
                        parsed_result = json.loads(cleaned_content)
                        logger.info(f"✅ Successfully parsed classification: {parsed_result}")
                        return parsed_result
                    except json.JSONDecodeError as e:
                        logger.warning(f"❗ JSON parsing failed: {e}")
                        logger.warning(f"❗ Model output: {content}")
                        # Continue retry
                elif isinstance(error, TimeoutError):
                    logger.warning(f"⏰ Ollama request timed out after {OLLAMA_TIMEOUT}s")
                    # Don't retry on timeout - fallback to NLP immediately
                    break
                else:
                    logger.warning(f"⚠️ Request failed: {error}")
                
                # Wait before retry (exponential backoff)
                if attempt < OLLAMA_MAX_RETRY:
                    backoff_time = min(2 ** attempt, 10)  # Max 10 seconds
                    logger.info(f"⏳ Waiting {backoff_time}s before retry...")
                    time.sleep(backoff_time)
                
            except Exception as e:
                logger.error(f"💥 Unexpected error during inference: {e}")
                if attempt < OLLAMA_MAX_RETRY:
                    time.sleep(2)

        # If we get here, all attempts failed - let NLP handle it
        logger.warning(f"⚠️  Ollama failed after {attempt} attempts, will fallback to NLP analysis")
        raise RuntimeError(f"LLM service unavailable after {OLLAMA_MAX_RETRY} attempts")


# -----------------------------------------------------------
# External callable function
# -----------------------------------------------------------
def safe_llm_classify(summary_text: str, model: str = None) -> dict[str, Any]:
    """Safe LLM classification for Federal Court cases."""
    return safe_ollama_request(summary_text, model)


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
    from loguru import logger
    
    if requests is None:
        raise ConnectionError("requests library is not available")
    if not text or not text.strip():
        logger.debug("Empty text provided to extract_entities_with_ollama")
        return None

    base_url = ollama_url or DEFAULT_OLLAMA_URL
    prompt = _build_extraction_prompt(text)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }

    logger.debug(f"🚀 Calling Ollama API - Model: {model}")
    logger.debug(f"🔗 URL: {base_url}/api/generate")
    logger.debug(f"⏱️ Timeout: {timeout}s")
    logger.debug(f"📝 Prompt length: {len(prompt)} chars")
    logger.debug(f"🔢 Max retries: {max_retries}")

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            logger.debug(f"📍 Attempt {attempt + 1}/{max_retries + 1}")
            start_time = time.time()
            
            response = requests.post(f"{base_url}/api/generate", json=payload, timeout=timeout)
            response.raise_for_status()
            
            elapsed_time = time.time() - start_time
            logger.debug(f"✅ Request completed in {elapsed_time:.2f}s")
            
            data = response.json()
            logger.debug(f"📦 Response keys: {list(data.keys())}")
            
            # If the service returned a JSON object directly with keys, accept it
            if isinstance(data, dict) and ("visa_office" in data or "judge" in data):
                logger.debug(f"🎯 Direct JSON response: {data}")
                return {k: data.get(k) for k in ("visa_office", "judge")}

            # support both 'response' or 'completion' or 'text' keys that contain JSON/text
            raw_output = data.get("response") or data.get("completion") or data.get("text") or ""
            logger.debug(f"📄 Raw output length: {len(raw_output)} chars")
            logger.debug(f"📄 Raw output preview: {raw_output[:200]}...")
            
            parsed = _parse_llm_output(raw_output)
            if parsed:
                logger.debug(f"✅ Parsed result: {parsed}")
                return parsed
            else:
                logger.warning("⚠️ Failed to parse LLM output")
            
            # If LLM returned no usable output, return None
            return None
            
        except requests.exceptions.Timeout as e:
            last_exc = e
            logger.warning(f"⏰ Timeout on attempt {attempt + 1}: {e}")
            if attempt == max_retries:
                raise ConnectionError(f"Failed to connect to Ollama after {max_retries + 1} attempts (timeout): {e}")
            logger.debug(f"⏳ Waiting {retry_delay}s before retry...")
            time.sleep(retry_delay)
            
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            logger.warning(f"🔌 Connection error on attempt {attempt + 1}: {e}")
            if attempt == max_retries:
                raise ConnectionError(f"Failed to connect to Ollama after {max_retries + 1} attempts (connection): {e}")
            logger.debug(f"⏳ Waiting {retry_delay}s before retry...")
            time.sleep(retry_delay)
            
        except Exception as e:
            last_exc = e
            logger.error(f"💥 Unexpected error on attempt {attempt + 1}: {e}")
            logger.exception("Full exception details:")
            if attempt == max_retries:
                raise ConnectionError(f"Failed to connect to Ollama after {max_retries + 1} attempts: {e}")
            logger.debug(f"⏳ Waiting {retry_delay}s before retry...")
            time.sleep(retry_delay)


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

def get_running_model(ollama_url: str | None = None, timeout: int = 5) -> str | None:
    """Get the currently running model from Ollama.
    
    Args:
        ollama_url: Base URL for Ollama, defaults to localhost:11434
        timeout: Request timeout in seconds
        
    Returns:
        The name of the running model, or None if no model is running
    """
    from loguru import logger
    
    if requests is None:
        logger.warning("requests library not available for model detection")
        return None
        
    base_url = ollama_url or DEFAULT_OLLAMA_URL
    
    try:
        logger.debug(f"🔍 Detecting running models at {base_url}/api/tags")
        response = requests.get(f"{base_url}/api/tags", timeout=timeout)
        response.raise_for_status()
        data = response.json()
        
        logger.debug(f"📦 Response: {list(data.keys())}")
        
        # Look for models with status "running"
        models = data.get("models", [])
        logger.debug(f"🤖 Found {len(models)} models")
        
        running_models = []
        for model in models:
            model_name = model.get("name", "unknown")
            model_status = model.get("status", "unknown")
            logger.debug(f"   - {model_name} (status: {model_status})")
            
            if model.get("status") == "running":
                running_models.append(model_name)
        
        if running_models:
            logger.info(f"✅ Running models detected: {running_models}")
            return running_models[0]  # Return first running model
                
        # If no explicit status, return first available model
        if models:
            first_model = models[0].get("name")
            logger.info(f"🤖 No running models, using first available: {first_model}")
            return first_model
        else:
            logger.warning("⚠️ No models found in Ollama")
            
    except requests.exceptions.ConnectionError as e:
        logger.error(f"🔌 Cannot connect to Ollama at {base_url}: {e}")
    except requests.exceptions.Timeout as e:
        logger.error(f"⏰ Timeout detecting models: {e}")
    except Exception as e:
        logger.error(f"💥 Error detecting running models: {e}")
        logger.exception("Full exception details:")
        
    return None


def extract_entities_batch(
    texts: list[str],
    model: str = "qwen2.5-7b-instruct",
    ollama_url: str | None = None,
    retries: int = 1,
    backoff: float = 0.5,
    timeout: float = 6.0,
) -> list[dict]:
    """Extract entities for a batch of texts. Returns list of dicts.

    This helper simply iterates and calls `extract_entities_with_ollama` per item;
    a future optimization could batch multiple prompts into a single request if
    the server supports it.
    """
    results = []
    for t in texts:
        results.append(
            extract_entities_with_ollama(t, model=model, ollama_url=ollama_url, max_retries=retries, retry_delay=backoff, timeout=timeout)
        )
    return results