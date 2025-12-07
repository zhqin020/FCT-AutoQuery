"""Case data model for Federal Court scraper.

This dataclass is intentionally simple and aligned with the scraper's
usage. The scraper constructs `Case` objects using the keyword `case_id`
and header fields such as `case_type`, `action_type`, `nature_of_proceeding`,
`filing_date`, `office`, `style_of_cause`, and `language`.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from src.lib.case_utils import canonicalize_case_number


@dataclass(init=False)
class Case:
    """Represents a scraped public case.

    This dataclass provides a backward-compatible constructor that accepts
    older field names used elsewhere in the codebase and tests, such as
    `case_number`, `case_title`, `court_name`, and `case_date`.
    """

    # canonical fields used throughout the scraper
    case_id: str
    case_type: Optional[str]
    action_type: Optional[str]
    nature_of_proceeding: Optional[str]
    filing_date: Optional[date]
    office: Optional[str]
    style_of_cause: Optional[str]
    language: Optional[str]
    url: Optional[str]
    html_content: str
    scraped_at: datetime

    def __init__(
        self,
        *,
        # canonical names
        case_id: Optional[str] = None,
        case_type: Optional[str] = None,
        action_type: Optional[str] = None,
        nature_of_proceeding: Optional[str] = None,
        filing_date: Optional[date] = None,
        office: Optional[str] = None,
        style_of_cause: Optional[str] = None,
        language: Optional[str] = None,
        url: Optional[str] = None,
        html_content: str = "",
        scraped_at: Optional[datetime] = None,
        # legacy / test-suite names
        case_number: Optional[str] = None,
        case_title: Optional[str] = None,
        court_name: Optional[str] = None,
        case_date: Optional[date] = None,
    ) -> None:
        # map legacy names to canonical fields and canonicalize the case id
        raw_case_id = case_id or case_number or ""
        try:
            self.case_id = canonicalize_case_number(raw_case_id)
        except Exception:
            self.case_id = raw_case_id
        self.case_type = case_type
        self.action_type = action_type
        self.nature_of_proceeding = nature_of_proceeding
        self.filing_date = filing_date or case_date
        self.office = office or court_name
        self.style_of_cause = style_of_cause or case_title
        self.language = language
        self.url = url
        self.html_content = html_content
        self.scraped_at = scraped_at or datetime.now()

    def to_dict(self) -> dict:
        """Convert case to dictionary for JSON export."""
        payload = {
            "case_id": self.case_id,
            "case_number": self.case_id,
            "title": self.style_of_cause,
            "court": self.office,
            "date": self.filing_date.isoformat() if self.filing_date else None,
            "case_type": self.case_type,
            "action_type": self.action_type,
            "nature_of_proceeding": self.nature_of_proceeding,
            "filing_date": self.filing_date.isoformat() if self.filing_date else None,
            "office": self.office,
            "style_of_cause": self.style_of_cause,
            "language": self.language,
            "url": self.url,
            "html_content": self.html_content,
            "scraped_at": self.scraped_at.isoformat(),
        }

        # Normalize docket_entries into the serialized output so callers
        # of `to_dict()` always receive the same shape. If the
        # attribute is present, serialize entries via `to_dict()` where
        # available; otherwise provide an empty list.
        entries = getattr(self, "docket_entries", None)
        if entries:
            try:
                payload["docket_entries"] = [
                    e.to_dict() if hasattr(e, "to_dict") else e for e in entries
                ]
            except Exception:
                payload["docket_entries"] = list(entries)
        else:
            payload["docket_entries"] = []

        return payload

    def to_csv_row(self) -> list:
        """Return a CSV row matching tests expectations:

        Columns: case_id, case_number, title, court, date, html_content, scraped_at
        """
        return [
            self.case_id,
            self.case_id,
            self.style_of_cause or "",
            self.office or "",
            self.filing_date.isoformat() if self.filing_date else "",
            self.html_content or "",
            self.scraped_at.isoformat() if self.scraped_at else "",
        ]

    # Backwards-compatible properties expected by older code/tests
    @property
    def case_number(self) -> str:
        return self.case_id

    @property
    def title(self) -> str:
        return self.style_of_cause or ""

    @property
    def court(self) -> str:
        return self.office or ""

    @classmethod
    def from_url(
        cls,
        url: str,
        case_number: str,
        title: str,
        court: str,
        case_date: date,
        html_content: str,
    ) -> "Case":
        """Create a Case instance from page URL and basic metadata.

        This method keeps a simple mapping so older code that calls
        `Case.from_url(...)` continues to work.
        """
        return cls(
            case_id=case_number,
            style_of_cause=title,
            office=court,
            filing_date=case_date,
            url=url,
            html_content=html_content,
        )
