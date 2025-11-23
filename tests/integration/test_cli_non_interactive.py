import json
import os
import subprocess
import time
from pathlib import Path


def test_auto_click_more_cli_non_interactive_creates_output(tmp_path):
    """Run the CLI in test-mode and verify a JSON output file is produced.

    The script supports a `TEST_FAKE_SERVICE=1` env var to avoid launching a
    browser during CI tests; this test uses that mode and the `--yes` flag to
    run non-interactively.
    """
    env = os.environ.copy()
    # Ensure output directory is clean
    out_dir = Path("output")
    if out_dir.exists():
        # remove any pre-existing test files with the case prefix
        for p in out_dir.glob("IMM-12345-25_*.json"):
            try:
                p.unlink()
            except Exception:
                pass

    # Run the script using the injectable FakeService to avoid browser usage.
    proc = subprocess.run(
        [
            "python",
            "scripts/auto_click_more.py",
            "--yes",
            "--service-class",
            "tests/integration/fake_service.py:FakeService",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    print(proc.stderr)
    assert (
        proc.returncode == 0
    ), f"Script exited with {proc.returncode}\nstderr:\n{proc.stderr}"

    # Give the script a moment to flush file system (shouldn't be needed but safe)
    time.sleep(0.1)

    # Check for an output JSON file
    files = list(out_dir.glob("IMM-12345-25_*.json"))
    assert files, "No output JSON files were created"

    # Validate JSON structure of the most recent file
    latest = max(files, key=lambda p: p.stat().st_mtime)
    with open(latest, "r", encoding="utf-8") as f:
        payload = json.load(f)

    assert "case" in payload
    assert payload["case"].get("case_id") == "IMM-12345-25"
    assert isinstance(payload.get("docket_entries"), list)
    # Cleanup the file we just created
    try:
        latest.unlink()
    except Exception:
        pass
