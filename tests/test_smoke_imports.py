import importlib


def test_smoke_imports():
    # Smoke tests to ensure common modules import cleanly
    modules = [
        'src.cli.main',
        'src.cli.tracking_integration',
        'src.lib.logging_config',
        'src.metrics_emitter',
        'src.services.batch_service',
        'src.services.case_tracking_service',
    ]
    for m in modules:
        mod = importlib.import_module(m)
        assert mod is not None
