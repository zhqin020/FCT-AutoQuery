from pathlib import Path
from typing import Optional


class BaseStorage:
    """Abstract storage interface used by batch runner for discovery and artifacts."""

    def exists(self, case_id: str) -> bool:  # pragma: no cover - trivial
        raise NotImplementedError()

    def save_failed_html(self, run_id: str, case_id: str, html: str) -> Optional[Path]:
        raise NotImplementedError()


class FileSystemStorage(BaseStorage):
    """Simple filesystem storage implementation.

    This implementation treats per-case JSON artifacts as proof of existence under
    `output/<per_case_subdir>/<case_id>.json`.
    """

    def __init__(self, output_dir: str = "output", per_case_subdir: str = "json"):
        self.base = Path(output_dir)
        self.per_case = self.base / per_case_subdir
        self.per_case.mkdir(parents=True, exist_ok=True)

    def exists(self, case_id: str) -> bool:
        # Look for a per-case JSON file as existence marker
        path = self.per_case / f"{case_id}.json"
        return path.exists()

    def save_failed_html(self, run_id: str, case_id: str, html: str) -> Optional[Path]:
        out_dir = self.base / "html_failed" / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{case_id}.html"
        try:
            with p.open("w", encoding="utf-8") as fh:
                fh.write(html)
            return p
        except Exception:
            return None
