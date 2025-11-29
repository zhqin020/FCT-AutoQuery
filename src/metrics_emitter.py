from typing import Dict, Any


class MetricsEmitter:
    """Minimal metrics emitter used by the batch runner.

    This small implementation stores emitted metrics in-memory which makes it
    trivial to test. The production implementation can reuse existing
    `run_logger`/metrics systems and provide the same API.
    """

    def __init__(self) -> None:
        self._metrics: Dict[str, Any] = {}

    def emit(self, name: str, value: float) -> None:
        """Emit a metric value.

        For testing we simply record the last value for each metric name.
        """
        if not name:
            raise ValueError("metric name required")
        self._metrics[name] = value

    def get(self, name: str) -> Any:
        return self._metrics.get(name)


# Module-level default emitter for simple imports in code and tests.
_default = MetricsEmitter()


def emit_metric(name: str, value: float) -> None:
    _default.emit(name, value)


def get_metric(name: str) -> Any:
    return _default.get(name)
