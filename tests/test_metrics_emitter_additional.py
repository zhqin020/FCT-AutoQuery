from src.metrics_emitter import emit_metric, get_metric


def test_emit_and_get_metric():
    emit_metric('test_metric', 3.14)
    assert get_metric('test_metric') == 3.14


def test_overwrite_metric():
    emit_metric('test_metric', 2.71)
    assert get_metric('test_metric') == 2.71
