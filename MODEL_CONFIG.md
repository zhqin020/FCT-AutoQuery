# Federal Court Analysis - Model Configuration Guide

## LLM Model Configuration

The system supports flexible LLM model configuration through TOML config files.

### Configuration Options

Create/edit your `config.toml` or `config.private.toml` file:

```toml
[analysis]
# Data source: "database", "directory", or "file"  
input_format = "database"
# Analysis mode: "rule" or "llm"
mode = "llm"

# LLM configuration
ollama_url = "http://localhost:11434"
# Option 1: Specify exact model to use
ollama_model = "qwen2.5-7b-instruct"
# Option 2: Leave commented to auto-detect running model
# ollama_model = "qwen2.5-7b-instruct"
ollama_timeout = 30

# Skip already analyzed cases
skip_analyzed = true
update_mode = "smart"
```

### Model Detection Behavior

1. **If `ollama_model` is specified**: Uses the configured model
2. **If `ollama_model` is not specified**: Automatically detects running model via `ollama ps`
3. **If no model is running**: Falls back to rule-based mode with warning

### Example Usage

```bash
# Check running models
ollama ps

# Your output should show something like:
# NAME        ID              SIZE      PROCESSOR    CONTEXT    UNTIL  
# qwen3:8b    500a1f067a9f    5.9 GB    100% CPU     4096       4 minutes from now

# The system will automatically use "qwen3:8b" if no specific model is configured
```

### Supported Models

Any model supported by Ollama should work, recommended models for legal analysis:
- `qwen2.5-7b-instruct`
- `qwen3:8b` 
- `llama3.1-8b`
- `gemma2-9b`

### Environment Variables (Alternative)

You can also use environment variables:

```bash
export FCT_ANALYSIS_OLLAMA_MODEL="qwen2.5-7b-instruct"
export FCT_ANALYSIS_OLLAMA_URL="http://localhost:11434"
export FCT_ANALYSIS_OLLAMA_TIMEOUT="30"
```