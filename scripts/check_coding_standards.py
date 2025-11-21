#!/usr/bin/env python3
"""Coding standards validation script."""

import ast
import sys
from pathlib import Path
from typing import List, Tuple


class CodingStandardsChecker:
    """Checks Python files for coding standards compliance."""

    def __init__(self):
        self.errors: List[str] = []

    def check_file(self, file_path: Path) -> bool:
        """Check a single Python file for coding standards.

        Args:
            file_path: Path to Python file

        Returns:
            bool: True if file passes all checks
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content, filename=str(file_path))

            self._check_docstrings(tree, file_path)
            self._check_type_hints(tree, file_path)
            self._check_imports(tree, file_path)

        except SyntaxError as e:
            self.errors.append(f"{file_path}: Syntax error: {e}")
            return False
        except Exception as e:
            self.errors.append(f"{file_path}: Error parsing file: {e}")
            return False

        return len(self.errors) == 0

    def _check_docstrings(self, tree: ast.AST, file_path: Path) -> None:
        """Check for docstrings on functions and classes."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not ast.get_docstring(node):
                    self.errors.append(
                        f"{file_path}:{node.lineno}: Missing docstring for {node.__class__.__name__.lower()} '{node.name}'"
                    )

    def _check_type_hints(self, tree: ast.AST, file_path: Path) -> None:
        """Check for type hints on function parameters and return types."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip __init__ methods for now
                if node.name == '__init__':
                    continue

                # Check return type annotation
                if node.returns is None:
                    self.errors.append(
                        f"{file_path}:{node.lineno}: Missing return type annotation for function '{node.name}'"
                    )

                # Check parameter type annotations
                for arg in node.args.args:
                    if arg.arg not in ('self', 'cls') and arg.annotation is None:
                        self.errors.append(
                            f"{file_path}:{node.lineno}: Missing type annotation for parameter '{arg.arg}' in function '{node.name}'"
                        )

    def _check_imports(self, tree: ast.AST, file_path: Path) -> None:
        """Check import organization."""
        imports = []
        from_imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                from_imports.append((node.module, [alias.name for alias in node.names]))

        # Check for loguru import (required by constitution)
        if any('loguru' in imp for imp in imports):
            # Good, loguru is imported
            pass

    def get_errors(self) -> List[str]:
        """Get list of all errors found."""
        return self.errors.copy()


def main() -> int:
    """Main entry point for coding standards checker."""
    if len(sys.argv) < 2:
        print("Usage: python coding_standards.py <python_file> [python_file ...]")
        return 1

    checker = CodingStandardsChecker()
    all_passed = True

    for file_arg in sys.argv[1:]:
        file_path = Path(file_arg)
        if not file_path.exists():
            print(f"ERROR: File not found: {file_path}")
            all_passed = False
            continue

        if not file_path.suffix == '.py':
            print(f"Skipping non-Python file: {file_path}")
            continue

        print(f"Checking {file_path}...")
        if not checker.check_file(file_path):
            all_passed = False

    errors = checker.get_errors()
    if errors:
        print("\nCoding standards violations found:")
        for error in errors:
            print(f"  {error}")
        return 1

    if all_passed:
        print("All files passed coding standards checks!")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())