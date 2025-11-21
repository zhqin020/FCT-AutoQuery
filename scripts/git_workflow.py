#!/usr/bin/env python3
"""Git workflow helper script."""

import subprocess
import sys
from pathlib import Path
from typing import Optional


def run_command(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        sys.exit(1)
    return result


def get_current_branch() -> str:
    """Get current git branch name."""
    result = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout.strip()


def validate_branch_name(branch: str) -> bool:
    """Validate branch name follows convention."""
    valid_prefixes = ["feat/", "fix/", "test/"]
    return any(branch.startswith(prefix) for prefix in valid_prefixes)


def run_tests() -> bool:
    """Run test suite."""
    print("Running tests...")
    result = run_command(["python", "-m", "pytest", "tests/"], check=False)
    if result.returncode != 0:
        print("Tests failed!")
        print(result.stdout)
        print(result.stderr)
        return False
    print("Tests passed!")
    return True


def run_linting() -> bool:
    """Run linting checks."""
    print("Running linting...")
    # Run flake8 if available
    result = run_command(["python", "-m", "flake8", "src/"], check=False)
    if result.returncode != 0:
        print("Linting failed!")
        print(result.stdout)
        return False
    print("Linting passed!")
    return True


def create_commit_message() -> str:
    """Generate a commit message based on branch and changes."""
    branch = get_current_branch()

    if branch.startswith("feat/"):
        prefix = "feat"
        description = branch[5:].replace("-", " ")
    elif branch.startswith("fix/"):
        prefix = "fix"
        description = branch[4:].replace("-", " ")
    elif branch.startswith("test/"):
        prefix = "test"
        description = branch[5:].replace("-", " ")
    else:
        prefix = "chore"
        description = branch.replace("-", " ")

    return f"{prefix}: {description}"


def commit_ready_workflow() -> None:
    """Run the complete TDD workflow: test, lint, commit."""
    print("=== Git Workflow: Commit Ready ===")

    # Validate branch
    branch = get_current_branch()
    if not validate_branch_name(branch):
        print(f"ERROR: Invalid branch name '{branch}'. Must start with feat/, fix/, or test/")
        sys.exit(1)

    # Run tests first (TDD: Red/Green/Refactor)
    if not run_tests():
        print("ERROR: Tests must pass before commit (TDD principle)")
        sys.exit(1)

    # Run linting
    if not run_linting():
        print("ERROR: Linting must pass before commit")
        sys.exit(1)

    # Check git status
    result = run_command(["git", "status", "--porcelain"])
    if not result.stdout.strip():
        print("No changes to commit")
        return

    # Add all changes
    print("Adding changes...")
    run_command(["git", "add", "."])

    # Generate commit message
    commit_msg = create_commit_message()
    print(f"Committing with message: '{commit_msg}'")

    # Commit
    run_command(["git", "commit", "-m", commit_msg])

    print("✅ Commit successful!")
    print("Next: Push your branch and create a pull request")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python git_workflow.py <command>")
        print("Commands:")
        print("  commit-ready  - Run tests, lint, and commit (TDD workflow)")
        print("  test          - Run tests only")
        print("  lint          - Run linting only")
        return

    command = sys.argv[1]

    if command == "commit-ready":
        commit_ready_workflow()
    elif command == "test":
        run_tests()
    elif command == "lint":
        run_linting()
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()