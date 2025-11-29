def test_import_cli_main():
    """Sanity test: importing the CLI main module should succeed."""
    import importlib

    mod = importlib.import_module('src.cli.main')
    assert mod is not None
