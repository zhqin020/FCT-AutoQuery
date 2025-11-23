"""DocketEntry data model for Federal Court scraper."""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class DocketEntry:
    """Represents individual recorded entries from the docket table.

    Attributes:
        id: Auto-incrementing ID (for database)
        court_file_no: References Case.court_file_no
        id_from_table: ID (sequence number from table)
        date_filed: Date Filed
        office: Office (submission location)
        recorded_entry_summary: Recorded Entry Summary
    """

    id: Optional[int] = None
    court_file_no: str = ""
    id_from_table: int = 0
    date_filed: Optional[date] = None
    office: Optional[str] = None
    recorded_entry_summary: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate the docket entry data after initialization."""
        self._validate()

    def _validate(self) -> None:
        """Validate docket entry data according to business rules."""
        if not self.case_id or not self.case_id.strip():
            raise ValueError("Case ID cannot be empty")

        if self.doc_id < 1:
            raise ValueError(f"Doc ID must be positive integer, got: {self.doc_id}")

        if not self.summary or not self.summary.strip():
            raise ValueError("Summary cannot be empty")

    @classmethod
    def from_dict(cls, data: dict) -> 'DocketEntry':
        """Create a DocketEntry instance from dictionary data.

        Args:
            data: Dictionary containing docket entry data

        Returns:
            DocketEntry: A validated DocketEntry instance
        """
        # Convert entry_date string to date if present
        entry_date = None
        if data.get('entry_date'):
            if isinstance(data['entry_date'], str):
                entry_date = date.fromisoformat(data['entry_date'])
            else:
                entry_date = data['entry_date']

        return cls(
            id=data.get('id'),
            case_id=data['case_id'],
            doc_id=data['doc_id'],
            entry_date=entry_date,
            entry_office=data.get('entry_office'),
            summary=data.get('summary'),
        )

    def to_dict(self) -> dict:
        """Convert docket entry to dictionary for JSON export.

        Returns:
            dict: Docket entry data as dictionary
        """
        return {
            "id": self.id,
            "case_id": self.case_id,
            "doc_id": self.doc_id,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "entry_office": self.entry_office,
            "summary": self.summary,
        }