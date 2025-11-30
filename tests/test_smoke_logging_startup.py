import subprocess
import sys
from pathlib import Path


def test_startup_logging_contains_program_invocation_and_proc_info(tmp_path):
    # Run a dry-run probe to produce startup logs
    env = dict(**sys.environ) if hasattr(sys, "environ") else None
    cmd = [sys.executable, "-m", "src.cli.main", "probe", "2025"]
    # Run the command; it writes logs to logs/scraper-1.log
    proc = subprocess.run(cmd, cwd=Path.cwd(), capture_output=True, text=True)
    # Ensure the process exited successfully
    assert proc.returncode == 0
    log_path = Path("logs") / "scraper-1.log"
    assert log_path.exists(), "Expected log file to exist"
    text = log_path.read_text(encoding="utf-8")
    assert "Program invocation:" in text
    assert "Parsed args:" in text
    assert "Process info:" in text or "Env keys" in text
