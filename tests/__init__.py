"""Test package marker to allow imports like `tests.utils.*`.

This file intentionally left minimal; its presence makes `tests` an importable
package so running `pytest` from the project root does not require setting
`PYTHONPATH=.` explicitly in some environments.
"""
