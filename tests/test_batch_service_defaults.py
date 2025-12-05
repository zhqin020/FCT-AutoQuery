from src.services.batch_service import BatchService
from src.lib.config import Config


def test_find_upper_bound_uses_config_defaults(monkeypatch):
    # Ensure Config returns a known probe budget and safe_stop
    monkeypatch.setattr(Config, 'get_probe_budget', classmethod(lambda cls: 6))
    monkeypatch.setattr(Config, 'get_safe_stop_no_records', classmethod(lambda cls: 2))

    # Define a check_case_exists that always returns False
    def check_case_exists(n: int) -> bool:
        return False

    # Call with explicit values
    upper_explicit, probes_explicit = BatchService.find_upper_bound(
        check_case_exists=check_case_exists,
        start=1,
        probe_budget=Config.get_probe_budget(),
        safe_stop=Config.get_safe_stop_no_records(),
        max_probes=100,
    )

    # Call without values to use Config defaults
    upper_default, probes_default = BatchService.find_upper_bound(
        check_case_exists=check_case_exists,
        start=1,
        probe_budget=None,
        safe_stop=None,
        max_probes=100,
    )

    assert probes_default == probes_explicit
    assert upper_default == upper_explicit
