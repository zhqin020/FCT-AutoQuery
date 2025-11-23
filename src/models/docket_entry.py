"""DocketEntry data model for Federal Court scraper.

This model aligns with the scraper which constructs entries using the
following keyword names: `case_id`, `doc_id`, `entry_date`, `entry_office`,
and `summary`.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class DocketEntry:
    """Represents individual recorded entries from the docket table.

    Attributes:
        id: Optional database id
        case_id: Court file number (e.g., 'IMM-12345-25')
        doc_id: Row/sequence id from the table
        entry_date: Date of the entry (optional)
        entry_office: Office where the entry was recorded (optional)
        summary: Recorded entry summary (optional)
    """

    id: Optional[int] = None
    case_id: str = ""
    doc_id: int = 0
    entry_date: Optional[date] = None
    entry_office: Optional[str] = None
    summary: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert docket entry to dictionary for JSON export."""
        return {
            "id": self.id,
            "case_id": self.case_id,
            "doc_id": self.doc_id,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "entry_office": self.entry_office,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DocketEntry":
        """Create a DocketEntry instance from a dict (best-effort).

        This helper is tolerant: date strings are converted if possible.
        """
        entry_date = data.get("entry_date")
        if isinstance(entry_date, str):
            try:
                entry_date = date.fromisoformat(entry_date)
            except Exception:
                entry_date = None

        return cls(
            id=data.get("id"),
            case_id=data.get("case_id", ""),
            doc_id=int(data.get("doc_id", 0) or 0),
            entry_date=entry_date,
            entry_office=data.get("entry_office"),
            summary=data.get("summary"),
        )
