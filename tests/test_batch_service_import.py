def test_import_batch_service():
    """Sanity test: importing the batch_service module should succeed."""
    import importlib

    mod = importlib.import_module('src.services.batch_service')
    assert mod is not None
