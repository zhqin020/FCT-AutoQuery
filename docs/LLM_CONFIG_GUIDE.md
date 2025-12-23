# LLM Configuration Management Guide

## 🎯 Overview
All LLM configuration is now **centrally managed** in `config.toml` to avoid conflicts and simplify management.

## 📍 Configuration Location

### Main Configuration File
**`config.toml`** - The single source of truth for all LLM settings:

```toml
[analysis]
# LLM Configuration (Centralized Settings)
# All LLM parameters are managed here - DO NOT modify in other files
ollama_url = "http://localhost:11434"
ollama_model = "qwen3:4b"
ollama_timeout = 240  # Timeout in seconds for LLM requests
```

## 🚫 Deprecated Files
- ~~`config.llm.toml`~~ - **Removed** (was causing conflicts)
- ~~Hardcoded values in `src/fct_analysis/llm.py`~~ - **Deprecated** (now fallback only)

## 🔧 Available Models

### Recommended Models
- `qwen3:4b` - Good balance of performance and accuracy (current default)
- `gemma2:2b` - Faster, lighter for CPU-only environments
- `llama3.1:8b` - Higher accuracy, requires more resources

### Model Selection Guide
| Model | Size | Speed | Accuracy | Best For |
|-------|------|-------|----------|-----------|
| gemma2:2b | 1.6GB | ⚡ Fast | ✅ Good | Quick analysis, CPU-only |
| qwen3:4b | 2.8GB | 🐇 Medium | 🎯 Great | Balanced performance |
| llama3.1:8b | 4.7GB | 🐢 Slow | 🏆 Excellent | High accuracy needs |

## ⏱️ Timeout Settings

### Recommended Timeouts
- **CPU-only**: 180-300 seconds
- **GPU available**: 60-120 seconds  
- **Large models (8B+)**: 300+ seconds

### Setting Timeout
```toml
[analysis]
ollama_timeout = 240  # Adjust based on your hardware and model
```

## 🔄 How to Change Model

### Method 1: Edit config.toml (Recommended)
```toml
[analysis]
ollama_model = "qwen3:4b"
ollama_timeout = 240
```

### Method 2: Environment Variable (Temporary)
```bash
export FCT_ANALYSIS_OLLAMA_MODEL="gemma2:2b"
export FCT_ANALYSIS_OLLAMA_TIMEOUT="180"
python src/fct_analysis/batch_case_analyzer.py cases.txt --mode llm
```

## 🔍 Configuration Precedence

Settings are applied in this order (higher priority wins):
1. **Environment variables** (`FCT_ANALYSIS_OLLAMA_*`)
2. **config.toml** file values
3. **Code defaults** (fallback only)

## ✅ Verification

Check which model is being used:
```bash
python src/fct_analysis/batch_case_analyzer.py test_case.txt --mode llm
# Look for: "🎯 Configured model: qwen3:4b"
```

## 🐛 Troubleshooting

### Model Not Available
```bash
ollama list  # Check available models
ollama pull qwen3:4b  # Download if needed
```

### Timeout Issues
1. Increase `ollama_timeout` in config.toml
2. Check system resources with `htop`
3. Consider using a smaller model

### Configuration Conflicts
If you suspect conflicts:
```bash
grep -r "ollama_model\|OLLAMA_MODEL" src/ --include="*.py"
# Should only show config.py reading from config files
```

## 📝 Migration Notes

### Before (Multiple Locations)
```python
# src/fct_analysis/llm.py
OLLAMA_MODEL = "qwen3:4b"
OLLAMA_TIMEOUT = 240

# config.llm.toml  
ollama_model = "qwen3:4b"
ollama_timeout = 360

# config.toml
ollama_model = "gemma2:2b"  # Conflict!
```

### After (Single Source of Truth)
```toml
# config.toml - ONLY place to configure LLM
[analysis]
ollama_model = "qwen3:4b"
ollama_timeout = 240
```

## 🎉 Benefits

- ✅ **Single Source of Truth**: No more conflicting configurations
- ✅ **Easy Management**: Change in one place applies everywhere
- ✅ **Clear Documentation**: All settings documented with comments
- ✅ **Flexible Overrides**: Environment variables still work for temporary changes
- ✅ **Automatic Fallbacks**: Graceful degradation if config is missing