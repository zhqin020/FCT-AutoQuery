# Coding Standards: Federal Court Case Scraper

## Python Standards

### Type Hints
- **MANDATORY**: All function parameters and return values MUST have type hints
- Use `typing` module imports for complex types
- Use `Union` for multiple possible types
- Use `Optional` for nullable types
- Example:
```python
from typing import Optional, List

def process_cases(cases: List[dict], output_dir: Optional[str] = None) -> bool:
    pass
```

### Docstrings
- **MANDATORY**: All public functions, classes, and modules MUST have Google-style docstrings
- Include description, Args, Returns, Raises sections
- Example:
```python
def scrape_case(url: str) -> Optional[Case]:
    """Scrape a single case from the provided URL.

    Args:
        url: The case URL to scrape

    Returns:
        Case object if successful, None if failed

    Raises:
        ScrapingError: If scraping fails due to network or parsing issues
    """
```

### Naming Conventions
- **Functions**: snake_case (e.g., `scrape_case()`, `validate_url()`)
- **Classes**: PascalCase (e.g., `CaseScraperService`, `URLValidator`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `DEFAULT_TIMEOUT`)
- **Variables**: snake_case (e.g., `case_data`, `output_dir`)

### Imports
- Standard library imports first
- Third-party imports second
- Local imports last
- Use absolute imports within the project
- Group imports with blank lines between groups

## Ethical Scraping Standards

### Rate Limiting
- **MANDATORY**: Minimum 1-second delay between requests
- Implement exponential backoff for retries
- Respect robots.txt (if present)
- Monitor and log all HTTP requests

### Data Access
- **MANDATORY**: Only access public URLs
- Never attempt login or authentication
- Validate URLs before access
- Log all access attempts with timestamps

### Error Handling
- Graceful degradation on failures
- Comprehensive logging of errors
- Continue processing on individual failures
- Never crash the entire application

## Code Quality

### Testing
- **MANDATORY**: 100% coverage for implemented modules
- Write tests before implementation (TDD)
- Mock external dependencies (network calls)
- Test both success and failure scenarios

### Error Handling
- Use custom exceptions for domain-specific errors
- Log errors with context
- Never expose sensitive information in error messages
- Handle edge cases gracefully

### Performance
- Minimize memory usage for large HTML content
- Use streaming for large data exports
- Implement timeouts for all network operations
- Profile and optimize bottlenecks

## File Structure

### Module Organization
```
src/
├── cli/           # Command-line interfaces
├── lib/           # Shared utilities and configuration
├── models/        # Data models
└── services/      # Business logic

tests/
├── contract/      # API contract tests
├── integration/   # End-to-end tests
└── unit/          # Unit tests
```

### File Naming
- Modules: snake_case (e.g., `case_scraper.py`)
- Test files: `test_*.py` (e.g., `test_case_scraper.py`)

## Git Workflow Integration

### Commit Messages
- Use imperative mood ("Add feature" not "Added feature")
- Reference issue numbers: "Fix login bug (#123)"
- Keep first line under 50 characters
- Add detailed description for complex changes

### Branch Naming
- `feat/description` for new features
- `fix/description` for bug fixes
- `test/description` for test improvements

## Validation

All code must pass:
- `flake8` linting
- `mypy` type checking
- `pytest` test suite with 80%+ coverage
- Pre-commit hooks

## Exceptions

Document any deviations from these standards in code comments with justification.