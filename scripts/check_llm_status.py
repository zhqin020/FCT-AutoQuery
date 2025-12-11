#!/usr/bin/env python3
"""LLM Service Status Checker

Utility script to check Ollama service status and available models.
"""

import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import requests
    from lib.config import Config
    from fct_analysis.llm import extract_entities_with_ollama
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure you're running this from the project root with the virtual environment activated")
    sys.exit(1)


def check_ollama_service():
    """Check if Ollama service is running and accessible."""
    ollama_url = Config.get_ollama_url()
    
    print(f"🔍 Checking Ollama service at: {ollama_url}")
    
    try:
        # Test basic connectivity
        response = requests.get(f"{ollama_url}/api/tags", timeout=5)
        response.raise_for_status()
        
        data = response.json()
        models = data.get("models", [])
        
        print("✅ Ollama service is running")
        print(f"📦 Available models: {len(models)}")
        
        for model in models:
            name = model.get("name", "Unknown")
            size_gb = model.get("size", 0) / (1024**3)
            details = model.get("details", {})
            param_size = details.get("parameter_size", "Unknown")
            quantization = details.get("quantization_level", "Unknown")
            
            print(f"  🤖 {name}")
            print(f"     Size: {size_gb:.1f} GB")
            print(f"     Parameters: {param_size}")
            print(f"     Quantization: {quantization}")
            
        return True, models
        
    except requests.exceptions.ConnectionError:
        print("❌ Ollama service is not running or not accessible")
        print(f"   Make sure Ollama is running at: {ollama_url}")
        print("   Start with: ollama serve")
        return False, []
    except Exception as e:
        print(f"❌ Error checking Ollama: {e}")
        return False, []


def test_llm_functionality(models):
    """Test actual LLM functionality with a simple extraction."""
    if not models:
        print("⚠️  No models available for testing")
        return
        
    # Use the first available model (prefer non-embedding models)
    test_model = None
    for model in models:
        if "embedding" not in model.get("name", "").lower():
            test_model = model.get("name")
            break
    
    if not test_model:
        test_model = models[0].get("name")
    
    print(f"\n🧪 Testing LLM functionality with model: {test_model}")
    
    # Test case text for entity extraction
    test_text = """
    Application for leave and judicial review against a decision from Beijing Visa Office.
    The case was heard by Justice Smith in Toronto.
    The applicant seeks to compel the immigration officer to process the delayed application.
    """
    
    try:
        ollama_url = Config.get_ollama_url()
        result = extract_entities_with_ollama(
            text=test_text,
            model=test_model,
            ollama_url=ollama_url,
            timeout=30
        )
        
        if result:
            print("✅ LLM functionality test passed")
            print("📋 Extraction results:")
            print(f"   Visa Office: {result.get('visa_office', 'Not detected')}")
            print(f"   Judge: {result.get('judge', 'Not detected')}")
        else:
            print("⚠️  LLM responded but no entities were extracted")
            
    except Exception as e:
        print(f"❌ LLM functionality test failed: {e}")


def check_configuration():
    """Display current LLM configuration."""
    print("\n⚙️  Current Configuration:")
    print(f"   Ollama URL: {Config.get_ollama_url()}")
    print(f"   Default Model: qwen2.5-7b-instruct (from code)")
    print(f"   Analysis Mode: {Config.get_analysis_mode()}")
    print(f"   Input Format: {Config.get_analysis_input_format()}")


def main():
    print("🚀 FCT-AutoQuery LLM Service Status Checker")
    print("=" * 50)
    
    # Check configuration first
    check_configuration()
    
    # Check Ollama service
    service_ok, models = check_ollama_service()
    
    if service_ok:
        # Test LLM functionality
        test_llm_functionality(models)
        
        print("\n📊 Summary:")
        print("✅ LLM service is available for analysis")
        print("💡 You can run LLM analysis with:")
        print("   python -m fct_analysis.cli --mode llm --input-format database")
        
    else:
        print("\n🔧 Troubleshooting:")
        print("1. Make sure Ollama is installed: https://ollama.ai")
        print("2. Start Ollama service: ollama serve")
        print("3. Pull a model: ollama pull qwen2.5-7b-instruct")
        print("4. Check if service is running: curl http://localhost:11434/api/tags")
        
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())