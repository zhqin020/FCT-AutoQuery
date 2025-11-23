"""Case data model for Federal Court scraper.

This dataclass is intentionally simple and aligned with the scraper's
usage. The scraper constructs `Case` objects using the keyword `case_id`
and header fields such as `case_type`, `action_type`, `nature_of_proceeding`,
`filing_date`, `office`, `style_of_cause`, and `language`.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Case:
    """Represents a scraped public case."""

    case_id: str
    case_type: Optional[str] = None
    action_type: Optional[str] = None
    nature_of_proceeding: Optional[str] = None
    filing_date: Optional[date] = None
    office: Optional[str] = None
    style_of_cause: Optional[str] = None
    language: Optional[str] = None
    url: Optional[str] = None
    html_content: str = ""
    scraped_at: datetime = field(default_factory=lambda: datetime.now())

    def to_dict(self) -> dict:
        """Convert case to dictionary for JSON export."""
        return {
            "case_id": self.case_id,
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
