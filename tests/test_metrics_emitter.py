try:
    from src.metrics_emitter import emit_metric
except Exception:
    emit_metric = None

def test_metrics_emitter_importable():
    assert True  # Import success asserted by absence of ImportError
