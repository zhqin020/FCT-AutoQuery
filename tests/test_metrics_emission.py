from metrics_emitter import emit_metric, get_metric, MetricsEmitter


def test_module_level_emitter_records_metric():
    emit_metric("batch.run.duration_seconds", 12.5)
    assert get_metric("batch.run.duration_seconds") == 12.5


def test_instance_emitter_behavior():
    m = MetricsEmitter()
    m.emit("batch.job.duration_seconds", 3.14)
    assert m.get("batch.job.duration_seconds") == 3.14


def test_emit_invalid_name_raises():
    m = MetricsEmitter()
    try:
        m.emit("", 1.0)
        assert False, "expected ValueError for empty metric name"
    except ValueError:
        pass
