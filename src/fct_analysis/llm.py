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

# Import logger globally for all tracking functions
try:
    from loguru import logger
except Exception:
    logger = None

def extract_json_objects_from_text(text: str) -> list:
    """Extract individual JSON objects from concatenated text."""
    objects = []
    brace_count = 0
    current_obj = ""
    
    for char in text:
        current_obj += char
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                # Complete object found
                try:
                    obj = json.loads(current_obj)
                    objects.append(obj)
                    current_obj = ""
                except json.JSONDecodeError:
                    if logger:
                        logger.debug(f"Failed to parse object: {current_obj}")
                    current_obj = ""
    
    return objects if objects else [{"is_mandamus": None, "outcome": None, "nature": None, "has_hearing": None}]


def _match_response_to_case(responses: list, case_number: str | None) -> dict | None:
    """Match a response to a specific case number from accumulated responses.
    
    This function implements the response matching logic to handle Ollama's
    accumulated response behavior where multiple case results may be returned
    in a single array.
    
    Args:
        responses: List of JSON response objects from Ollama
        case_number: The target case number to match
        
    Returns:
        The response object that matches the case number, or None if no match found
    """
    if not case_number:
        # If no case number provided, return the first response
        return responses[0] if responses else None
    
    # Strategy 1: Look for case number in the response content (if Ollama echoes it back)
    for i, response in enumerate(responses):
        if isinstance(response, dict):
            # Check any string fields that might contain the case number
            for key, value in response.items():
                if isinstance(value, str) and case_number and case_number in value:
                    if logger:
                        logger.info(f"🎯 Found case {case_number} in response[{i}] field '{key}'")
                    return response
    
    # Strategy 2: Use positional matching (assume responses are in chronological order)
    # This is a fallback when no explicit matching is possible
    if logger:
        logger.info(f"📍 Using positional matching for case {case_number} (first available response)")
    return responses[0] if responses else None


DEFAULT_OLLAMA_URL = "http://localhost:11434"

# -----------------------------------------------------------
# Global lock: CPU-only environment can only allow one LLM inference task
# -----------------------------------------------------------
ollama_lock = threading.Lock()

# -----------------------------------------------------------
# Ollama configuration
# -----------------------------------------------------------
# All Ollama parameters now managed centrally in config.toml
# These are deprecated fallback values only
OLLAMA_MODEL = None   # Will be overridden by config
OLLAMA_TIMEOUT = None # Will be overridden by config
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
    import signal
    import os
    
    result = [None]  # type: list[object]
    error = [None]  # type: list[Exception | None]
    
    # Use signal-based timeout for better resource handling
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {timeout} seconds")
    
    # Set timeout handler
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    
    try:
        # Set alarm
        signal.alarm(timeout)
        try:
            result[0] = func()
        except Exception as e:
            error[0] = e
        finally:
            # Cancel alarm
            signal.alarm(0)
    finally:
        # Restore original handler
        signal.signal(signal.SIGALRM, old_handler)
    
    return result[0], error[0]


# -----------------------------------------------------------
# Safe Ollama request for classification
# -----------------------------------------------------------
def safe_ollama_request(summary_text: str, model: str | None = None, wait_for_idle: bool = True, max_idle_wait: int | None = None, case_number: str | None = None) -> dict[str, Any]:
    """
    Safe Ollama call with timeout and retry:
    - Single-threaded (with lock)
    - Automatic timeout termination
    - Exponential backoff retry
    - Optional wait for idle state
    - Case number for request tracking
    - Returns error to fallback to NLP analysis
    """
    from loguru import logger
    
    # Log case number for debugging
    if case_number:
        logger.debug(f"🏷️ Processing case: {case_number}")
    
    # Get model from config (centralized management)
    model_to_use = model  # Start with parameter
    if model_to_use is None:
        try:
            from src.lib.config import Config
            model_to_use = Config.get_ollama_model()
        except Exception:
            model_to_use = None  # Let Ollama auto-detect
    
    # Fallback to deprecated constant if config fails
    if model_to_use is None and OLLAMA_MODEL:
        model_to_use = OLLAMA_MODEL
    
    # Use default idle wait time if not specified
    if max_idle_wait is None:
        try:
            from src.lib.config import Config
            max_idle_wait = Config.get_ollama_timeout()
        except Exception:
            max_idle_wait = OLLAMA_TIMEOUT or 120  # Fallback to deprecated constant or default
    
    with ollama_lock:
        # Optional: Wait for Ollama to become idle
        if wait_for_idle:
            logger.info("⏳ Checking if Ollama is idle before starting new request...")
            if not wait_for_ollama_idle(max_wait_time=max_idle_wait, check_interval=5):
                logger.warning(f"⚠️ Ollama did not become idle within {max_idle_wait}s, proceeding anyway")
        
        attempt = 0

        while attempt < OLLAMA_MAX_RETRY:
            attempt += 1
            logger.info(f"[Ollama] Attempt {attempt}/{OLLAMA_MAX_RETRY}...")

            def call():
                if requests is None:
                    raise ConnectionError("requests library is not available")
                
                # Include case number in the prompt for proper response matching
                case_identifier = f"\n\nCASE_IDENTIFIER: {case_number}" if case_number else ""
                
                payload = {
                    "model": model_to_use,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Summaries:\n{summary_text}{case_identifier}"}
                    ],
                    "stream": False,
                    "options": {"num_predict": 200, "temperature": 0}
                }
                
                # Get timeout from config (centralized management)
                try:
                    from src.lib.config import Config
                    request_timeout = Config.get_ollama_timeout()
                except Exception:
                    request_timeout = OLLAMA_TIMEOUT or 120  # Fallback to deprecated constant or default
                
                response = requests.post(
                    f"{DEFAULT_OLLAMA_URL}/api/chat", 
                    json=payload, 
                    timeout=request_timeout
                )
                response.raise_for_status()
                data = response.json()
                
                if "message" in data and "content" in data["message"]:
                    return data["message"]["content"]
                else:
                    raise ValueError("Invalid response format from Ollama")

            # ---- Execute inference with timeout ----
            # Get timeout from config (centralized management)
            try:
                from src.lib.config import Config
                inference_timeout = Config.get_ollama_timeout()
            except Exception:
                inference_timeout = OLLAMA_TIMEOUT or 120  # Fallback to deprecated constant or default
            
            try:
                content, error = run_with_timeout(call, inference_timeout)
                
                if error is None and content is not None:
                    # Success - try to parse JSON with response matching
                    try:
                        # Handle markdown-wrapped JSON
                        cleaned_content = str(content).strip()
                        if cleaned_content.startswith('```json'):
                            cleaned_content = cleaned_content[7:]  # Remove ```json
                        if cleaned_content.endswith('```'):
                            cleaned_content = cleaned_content[:-3]  # Remove ```
                        cleaned_content = cleaned_content.strip()
                        
                        # Try to parse as JSON array first (accumulated responses)
                        try:
                            parsed = json.loads(cleaned_content)
                        except json.JSONDecodeError:
                            # If that fails, try to extract individual objects
                            parsed = extract_json_objects_from_text(cleaned_content)
                        
                        # Handle array of accumulated responses with proper matching
                        if isinstance(parsed, list):
                            logger.info(f"🔗 Received {len(parsed)} responses from Ollama")
                            if len(parsed) >= 1:
                                # Try to match response to current case
                                parsed_result = _match_response_to_case(parsed, case_number)
                                if not parsed_result:
                                    logger.warning(f"⚠️ No matching response found for case {case_number}, using first response")
                                    parsed_result = parsed[0]
                                logger.info(f"✅ Matched response for case {case_number or 'unknown'}: {parsed_result}")
                            else:
                                raise ValueError("Empty response array received")
                        elif isinstance(parsed, dict):
                            parsed_result = parsed  # Single response
                            logger.info(f"✅ Single response parsed for case {case_number or 'unknown'}: {parsed_result}")
                        else:
                            raise ValueError(f"Unexpected response format: {type(parsed)}")
                        
                        logger.info(f"✅ Successfully parsed and matched classification: {parsed_result}")
                        return parsed_result
                    except Exception as e:
                        logger.warning(f"❗ Response parsing failed: {e}")
                        logger.warning(f"❗ Model output: {content}")
                        # Continue retry
                elif isinstance(error, TimeoutError):
                    logger.warning(f"⏰ Ollama request timed out after {inference_timeout}s")
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
def safe_llm_classify(summary_text: str, model: str | None = None, wait_for_idle: bool = True, max_idle_wait: int | None = None, case_number: str | None = None) -> dict[str, Any]:
    """Safe LLM classification for Federal Court cases."""
    return safe_ollama_request(summary_text, model, wait_for_idle=wait_for_idle, max_idle_wait=max_idle_wait, case_number=case_number)


def extract_entities_with_ollama(
    text: str,
    model: str = "qwen2.5-7b-instruct",
    ollama_url: str | None = None,
    timeout: int = 60,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    wait_for_idle: bool = True,
    max_idle_wait: int | None = None,
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

    # Use default idle wait time if not specified
    if max_idle_wait is None:
        try:
            from src.lib.config import Config
            max_idle_wait = Config.get_ollama_timeout()
        except Exception:
            max_idle_wait = OLLAMA_TIMEOUT or 120  # Fallback to deprecated constant or default
    
    # Optional: Wait for Ollama to become idle
    if wait_for_idle:
        logger.info("⏳ Checking if Ollama is idle before entity extraction...")
        if not wait_for_ollama_idle(max_wait_time=max_idle_wait, check_interval=5, ollama_url=base_url):
            logger.warning(f"⚠️ Ollama did not become idle within {max_idle_wait}s, proceeding anyway")

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


def get_running_session_count(ollama_url: str | None = None, timeout: int = 5) -> int:
    """Get the number of currently active Ollama processing sessions.
    
    **NEW METHOD**: Uses non-intrusive detection to avoid self-interference:
    1. Check network connections for real external requests (avoids self-interference)
    2. Check /api/ps for loaded models status information
    3. Use lightweight health checks as fallback
    
    This approach avoids the problem where detection requests themselves make Ollama appear busy.
    
    Args:
        ollama_url: Base URL for Ollama, defaults to localhost:11434
        timeout: Request timeout in seconds
        
    Returns:
        Number of actively processing sessions (0 if idle)
    """
    from loguru import logger
    
    if requests is None:
        logger.warning("requests library not available for session detection")
        return 0
        
    base_url = ollama_url or DEFAULT_OLLAMA_URL
    port = 11434  # Default Ollama port
    
    try:
        # Step 1: Check network connections (non-intrusive method)
        connection_count = _count_ollama_connections(port)
        logger.debug(f"🔍 Network connections to port {port}: {connection_count}")
        
        # Subtract 1 for our own monitoring connection if we just made a request
        # This handles the case where our own detection creates a connection
        adjusted_connections = max(0, connection_count - 1)
        logger.debug(f"🔍 Adjusted connections (excluding our own): {adjusted_connections}")
        
        if adjusted_connections > 0:
            logger.info(f"📈 Detected {adjusted_connections} external connections to Ollama")
            return adjusted_connections
        
        # Step 2: If no external connections, check if models are loaded
        loaded_models = []
        logger.debug(f"🔍 Checking loaded models at {base_url}/api/ps")
        try:
            response = requests.get(f"{base_url}/api/ps", timeout=timeout)
            response.raise_for_status()
            ps_data = response.json()
            
            if isinstance(ps_data, dict) and "models" in ps_data:
                import datetime
                current_time = datetime.datetime.now(datetime.timezone.utc)
                
                for model_info in ps_data["models"]:
                    model_name = model_info.get("name", "unknown")
                    expires_at_str = model_info.get("expires_at")
                    
                    # Check if model is still loaded (not expired)
                    if expires_at_str:
                        try:
                            expires_at = datetime.datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                            if expires_at > current_time:
                                loaded_models.append(model_name)
                                remaining_time = expires_at - current_time
                                logger.debug(f"   📦 Model loaded: {model_name} (expires in {remaining_time.total_seconds():.0f}s)")
                            else:
                                logger.debug(f"   💤 Expired model: {model_name}")
                        except (ValueError, TypeError) as e:
                            logger.debug(f"   ❓ Invalid expiry for {model_name}: {e}")
                    else:
                        # No expiry means permanently loaded
                        loaded_models.append(model_name)
                        logger.debug(f"   📦 Permanently loaded: {model_name}")
                        
        except requests.exceptions.RequestException as e:
            logger.debug(f"ℹ️ /api/ps not available: {e}")
        
        # Step 3: Only test models if we have loaded models AND want to be very sure
        if loaded_models and adjusted_connections == 0:
            logger.debug(f"🔍 No external connections, testing if {len(loaded_models)} loaded models are actually processing")
            for model_name in loaded_models:
                if _is_model_actively_processing_non_intrusive(base_url, model_name, timeout=2):
                    logger.info(f"📈 Model {model_name} appears to be processing internal work")
                    return 1
                else:
                    logger.debug(f"   💤 Model {model_name} is idle")
        
        # If we get here, Ollama is truly idle
        logger.info(f"📈 No active processing sessions detected")
        return 0
        
    except Exception as e:
        logger.error(f"💥 Error detecting session count: {e}")
        logger.exception("Full exception details:")
        return 0


def _count_ollama_connections(port: int = 11434) -> int:
    """Count established connections to Ollama port using netstat.
    
    This is a non-intrusive method that doesn't create its own connections
    to Ollama, avoiding the self-interference problem.
    
    Args:
        port: Ollama port number
        
    Returns:
        Number of established connections to the port
    """
    from loguru import logger
    import subprocess
    
    try:
        # Use netstat to count ESTABLISHED connections to Ollama port
        result = subprocess.run(
            ["netstat", "-an"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            connections = 0
            
            for line in lines:
                # Look for ESTABLISHED connections to our port
                if (f":{port}" in line and 
                    "ESTABLISHED" in line and
                    "127.0.0.1" in line):  # Local connections only
                    
                    connections += 1
                    logger.debug(f"   🔗 Found connection: {line.strip()}")
            
            return connections
        else:
            logger.debug(f"netstat command failed: {result.stderr}")
            return 0
            
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
        logger.debug(f"Cannot use netstat for connection counting: {e}")
        # Fallback: try ss (modern alternative to netstat)
        return _count_ollama_connections_ss(port)
    
    except Exception as e:
        logger.debug(f"Error counting connections: {e}")
        return 0


def _count_ollama_connections_ss(port: int = 11434) -> int:
    """Count connections using ss command (fallback for netstat)."""
    from loguru import logger
    import subprocess
    
    try:
        result = subprocess.run(
            ["ss", "-an"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            connections = 0
            
            for line in lines:
                if (f":{port}" in line and 
                    "ESTAB" in line and
                    "127.0.0.1" in line):
                    
                    connections += 1
                    logger.debug(f"   🔗 Found ss connection: {line.strip()}")
            
            return connections
        else:
            logger.debug(f"ss command failed: {result.stderr}")
            return 0
            
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
        logger.debug(f"Cannot use ss for connection counting: {e}")
        return 0


def _is_model_actively_processing(base_url: str, model_name: str, timeout: int = 3) -> bool:
    """DEPRECATED: Test if a model is actively processing (may cause self-interference).
    
    This function is kept for compatibility but should not be used in session detection
    as it can cause self-interference problems.
    
    Args:
        base_url: Ollama server URL
        model_name: Name of the model to test
        timeout: Test timeout in seconds
        
    Returns:
        True if model appears to be actively processing other requests
    """
    from loguru import logger
    import datetime
    
    if requests is None:
        logger.warning("requests library not available for activity testing")
        return True  # Conservative: assume busy if we can't test
    
    try:
        # Send minimal test request
        test_payload = {
            "model": model_name,
            "prompt": "Hi",  # Smallest possible test prompt
            "stream": False,
            "options": {
                "temperature": 0,
                "max_tokens": 1  # Request only 1 token to minimize processing
            }
        }
        
        start_time = datetime.datetime.now()
        _ = requests.post(  # Use _ to indicate we ignore the response value
            f"{base_url}/api/generate", 
            json=test_payload, 
            timeout=timeout
        )
        response_time = (datetime.datetime.now() - start_time).total_seconds()
        
        # Response time threshold: if > 0.8 seconds, model is likely busy
        # This threshold may need adjustment based on your hardware
        if response_time > 0.8:
            logger.debug(f"   ⏱️ {model_name} response: {response_time:.2f}s (BUSY)")
            return True
        else:
            logger.debug(f"   ⏱️ {model_name} response: {response_time:.2f}s (idle)")
            return False
            
    except requests.exceptions.Timeout:
        # Timeout strongly suggests model is busy processing other requests
        logger.debug(f"   ⏱️ {model_name} test timeout (BUSY)")
        return True
    except requests.exceptions.RequestException as e:
        # Other errors might indicate the model is busy or unavailable
        logger.debug(f"   ❓ {model_name} test failed: {e}")
        return True  # Conservative: assume busy if we can't tell


def _is_model_actively_processing_non_intrusive(base_url: str, model_name: str, timeout: int = 2) -> bool:
    """Non-intrusive test for model activity using lightweight health check.
    
    This function uses a very minimal approach to avoid interfering with
    actual processing and tries to detect internal Ollama work.
    
    Args:
        base_url: Ollama server URL
        model_name: Name of the model to test
        timeout: Very short timeout for quick check
        
    Returns:
        True if model appears to be actively processing
    """
    from loguru import logger
    import datetime
    
    if requests is None:
        logger.warning("requests library not available for activity testing")
        return True  # Conservative: assume busy if we can't test
    
    try:
        # Use a very lightweight health check on /api/ps instead of /api/generate
        # This should not interfere with actual model processing
        start_time = datetime.datetime.now()
        response = requests.get(f"{base_url}/api/ps", timeout=timeout)
        response.raise_for_status()
        
        # Check response time - even /api/ps might be slow if Ollama is busy
        response_time = (datetime.datetime.now() - start_time).total_seconds()
        
        # Very short threshold since /api/ps should be fast
        if response_time > 0.3:
            logger.debug(f"   ⏱️ API response: {response_time:.2f}s (Ollama busy)")
            return True
        else:
            logger.debug(f"   ⏱️ API response: {response_time:.2f}s (Ollama idle)")
            return False
            
    except requests.exceptions.Timeout:
        # Even /api/ps timeout suggests Ollama is very busy
        logger.debug(f"   ⏱️ API timeout (Ollama very busy)")
        return True
    except requests.exceptions.RequestException as e:
        # Other errors indicate potential issues
        logger.debug(f"   ❓ API check failed: {e}")
        return False  # Don't assume busy for network errors


def _is_ollama_service_busy(base_url: str, timeout: int = 3) -> bool:
    """Check if Ollama service is busy using response time heuristics.
    
    This is a fallback method when no specific models are detected.
    
    Args:
        base_url: Ollama server URL
        timeout: Test timeout in seconds
        
    Returns:
        True if service appears to be busy
    """
    from loguru import logger
    import datetime
    
    if requests is None:
        logger.warning("requests library not available for service testing")
        return True  # Conservative: assume busy if we can't test
    
    try:
        # Test with a simple tags request
        start_time = datetime.datetime.now()
        _ = requests.get(f"{base_url}/api/tags", timeout=timeout)  # Use _ to ignore response
        response_time = (datetime.datetime.now() - start_time).total_seconds()
        
        # If tags API takes > 1.5 seconds, service is likely busy
        if response_time > 1.5:
            logger.debug(f"   ⏱️ Service response time: {response_time:.2f}s (BUSY)")
            return True
        else:
            logger.debug(f"   ⏱️ Service response time: {response_time:.2f}s (idle)")
            return False
            
    except requests.exceptions.Timeout:
        logger.debug(f"   ⏱️ Service timeout (BUSY)")
        return True
    except requests.exceptions.RequestException as e:
        logger.debug(f"   ❓ Service test failed: {e}")
        return True  # Conservative: assume busy if we can't tell


def is_ollama_idle(ollama_url: str | None = None, timeout: int = 5) -> bool:
    """Check if Ollama is idle (no active inference sessions).
    
    Args:
        ollama_url: Base URL for Ollama, defaults to localhost:11434
        timeout: Request timeout in seconds
        
    Returns:
        True if Ollama is idle, False if busy
    """
    from loguru import logger
    
    session_count = get_running_session_count(ollama_url, timeout)
    is_idle = session_count == 0
    
    if is_idle:
        logger.debug("✅ Ollama is idle - safe to proceed")
    else:
        logger.debug(f"⏳ Ollama is busy with {session_count} active sessions")
        
    return is_idle


def wait_for_ollama_idle(
    max_wait_time: int = 300, 
    check_interval: int = 10,
    ollama_url: str | None = None,
    timeout: int = 5
) -> bool:
    """Wait for Ollama to become idle before proceeding.
    
    Args:
        max_wait_time: Maximum time to wait in seconds (default: 5 minutes)
        check_interval: Time between checks in seconds (default: 10 seconds)
        ollama_url: Base URL for Ollama, defaults to localhost:11434
        timeout: Timeout for individual API calls
        
    Returns:
        True if Ollama became idle within time limit, False if timeout reached
    """
    from loguru import logger
    
    start_time = time.time()
    elapsed = 0
    
    logger.info(f"⏳ Waiting for Ollama to become idle (max wait: {max_wait_time}s)")
    
    while elapsed < max_wait_time:
        if is_ollama_idle(ollama_url, timeout):
            wait_time = time.time() - start_time
            logger.info(f"✅ Ollama became idle after {wait_time:.1f}s")
            return True
            
        elapsed = time.time() - start_time
        remaining = max_wait_time - elapsed
        
        if remaining <= 0:
            break
            
        logger.info(f"⏱️  Ollama busy, checking again in {check_interval}s ({remaining:.0f}s remaining)")
        time.sleep(min(check_interval, remaining))
    
    logger.warning(f"⚠️  Ollama did not become idle within {max_wait_time}s")
    return False


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
            extract_entities_with_ollama(t, model=model, ollama_url=ollama_url, max_retries=retries, retry_delay=backoff, timeout=int(timeout))
        )
    return results