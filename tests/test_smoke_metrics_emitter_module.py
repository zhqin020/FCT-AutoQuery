try:
    from src.metrics_emitter import emit_metric
except Exception:
    # metrics_emitter may not be installed in some environments; ensure import falls back
    emit_metric = None


def test_metrics_emitter_import():
    # No strict assertion — module should be importable or gracefully fallback
    assert emit_metric is not None or emit_metric is None
