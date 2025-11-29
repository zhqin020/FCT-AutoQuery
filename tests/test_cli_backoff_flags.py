import sys

from src.cli.main import main


def test_cli_backoff_flags_applied(monkeypatch, capsys):
    # Capture the rate_limiter passed into BatchService.find_upper_bound
    def fake_find_upper_bound(*args, **kwargs):
        rl = kwargs.get("rate_limiter")
        assert rl is not None, "rate_limiter was not passed to find_upper_bound"
        # Verify CLI-provided tuning values are applied
        assert abs(rl.interval_seconds - 2.5) < 1e-6
        assert abs(rl.backoff_factor - 3.3) < 1e-6
        assert abs(rl.max_backoff_seconds - 77.0) < 1e-6
        return (123, 1)

    monkeypatch.setattr("src.services.batch_service.BatchService.find_upper_bound", fake_find_upper_bound)

    # Place global tuning flags before the subcommand so argparse parses them as globals
    monkeypatch.setattr(sys, "argv", [
        "prog",
        "--rate-interval",
        "2.5",
        "--backoff-factor",
        "3.3",
        "--max-backoff-seconds",
        "77",
        "probe",
        "2025",
        "--probe-budget",
        "5",
    ])

    # Run CLI main; fake_find_upper_bound will assert the limiter params
    main()

    out = capsys.readouterr().out
    assert "Approx upper numeric id: 123" in out
