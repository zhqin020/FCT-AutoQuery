# Git Workflow: Federal Court Case Scraper

## Overview
This project follows **Trunk-Based Development** with **Test-First Development (TDD)** approach.

## Workflow Steps

### 1. Issue Creation
- **MANDATORY**: All work starts with a GitHub issue
- Issues are stored in `issues/` folder with format: `XXXX-description.md`
- Current issue: `issues/0001-federal-court-scraper.md`

### 2. Branch Creation
```bash
# Create feature branch from main
git checkout main
git pull origin main
git checkout -b feat/0001-federal-court-scraper
```

**Branch Naming Rules:**
- `feat/description` - New features
- `fix/description` - Bug fixes
- `test/description` - Test improvements

### 3. Test-First Development (TDD)
```bash
# 1. Write failing test FIRST
pytest tests/ -k "test_case_scraper"  # Should fail

# 2. Implement minimal code to pass
# Edit src/services/case_scraper_service.py

# 3. Run tests to verify
pytest tests/ -k "test_case_scraper"  # Should pass

# 4. Refactor while keeping tests passing
```

### 4. Commit Standards
```bash
# Stage changes
git add src/services/case_scraper_service.py tests/test_case_scraper.py

# Commit with issue reference
git commit -m "feat: implement basic case scraper service (#1)

- Add CaseScraperService class
- Implement URL validation
- Add basic HTML extraction
- Write comprehensive tests"
```

**Commit Message Format:**
```
type: description (#issue)

- Bullet point details
- More details
```

### 5. Pre-commit Validation
Automatic checks run on every commit:
- ✅ Branch naming validation
- ✅ Test execution
- ✅ Code linting (flake8)
- ✅ Type checking (mypy)

### 6. Pull Request
```bash
# Push branch
git push origin feat/0001-federal-court-scraper

# Create PR with title: "feat: implement federal court case scraper (#1)"
# PR description should reference the issue and include testing results
```

### 7. Code Review & Merge
- Automated CI/CD runs all tests
- Code review ensures standards compliance
- Squash merge to main
- Delete feature branch immediately

### 8. Issue Closure
- Issue automatically closes via PR merge
- Issue status updated to "CLOSED"

## Quality Gates

### Pre-commit
- Branch naming: `feat|fix|test/*`
- Tests pass: `pytest` successful
- Linting: `flake8` clean
- Types: `mypy` clean

### Pre-merge
- All tests pass
- Code coverage ≥80%
- No critical security issues
- Documentation updated

## Development Commands

```bash
# Setup development environment
conda activate fct
pip install -e .[dev]

# Run tests
pytest tests/
pytest tests/ -k "case" --cov=src

# Run linting
flake8 src/
mypy src/

# Format code
black src/
isort src/

# Run pre-commit checks
pre-commit run --all-files
```

## Issue Lifecycle

1. **Open**: Issue created with requirements
2. **In Progress**: Branch created, work started
3. **In Review**: PR created, under review
4. **Closed**: Merged to main, issue resolved

## Branch Protection

- `main` branch: Requires PR, tests pass, review approval
- Feature branches: Can force push during development
- No direct commits to main allowed

## Rollback Strategy

If issues arise after merge:
1. Create hotfix branch: `fix/critical-bug`
2. Implement fix with tests
3. Create PR and merge
4. Deploy rollback if needed

## Metrics

- Test coverage: ≥80%
- Build time: <5 minutes
- Time to review: <24 hours
- Deployment frequency: Multiple per day