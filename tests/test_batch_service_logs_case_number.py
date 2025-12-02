from src.services.batch_service import BatchService


def test_find_upper_bound_logs_case_number(monkeypatch):
    # Use loguru sink to capture logger output
    from src.lib.logging_config import get_logger
    import io

    import os
    # Ensure probe-state persistence is disabled for this test to avoid log suppression
    os.environ["FCT_PERSIST_PROBE_STATE"] = "false"
    logger = get_logger()
    buf = io.StringIO()
    sink_id = logger.add(buf, level="INFO", format="{message}")

    # Return True for the number 1 only, false otherwise
    def fast_check(n):
        return n == 1

    def check(n):
        return False

    upper, probes = BatchService.find_upper_bound(
        check_case_exists=check,
        fast_check_case_exists=fast_check,
        start=1,
        initial_high=3,
        probe_budget=2,
        collect=False,
        max_probes=10,
        format_case_number=lambda n: f"IMM-{n}-21",
    )

    # Read captured messages
    content = buf.getvalue()
    logger.remove(sink_id)
    assert "Probing IMM-1-21" in content
    assert "Probing IMM-2-21" in content
