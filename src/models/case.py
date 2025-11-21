"""Case data model for Federal Court scraper."""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional
import uuid


@dataclass
class Case:
    """Represents a scraped public case with metadata and HTML content.

    Attributes:
        case_id: Unique identifier for the case (URL or generated ID)
        case_number: Case number containing "IMM-"
        title: Case title
        court: Court name (Federal Court)
        date: Case date
        html_content: Full HTML content of the case
        scraped_at: When data was collected
    """

    case_id: str
    case_number: str
    title: str
    court: str
    date: date
    html_content: str
    scraped_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Validate the case data after initialization."""
        self._validate()

    def _validate(self) -> None:
        """Validate case data according to business rules."""
        if not self.case_number or "IMM-" not in self.case_number:
            raise ValueError(f"Case number must contain 'IMM-', got: {self.case_number}")

        if not self.html_content or not self.html_content.strip():
            raise ValueError("HTML content cannot be empty")

        if not self.case_id or not self.case_id.strip():
            raise ValueError("Case ID cannot be empty")

        # Note: Date validation for 2023-2025/ongoing is handled at scraping level

    @classmethod
    def from_url(cls, url: str, case_number: str, title: str, court: str,
                 case_date: date, html_content: str):
        """Create a Case instance from URL and scraped data.

        Args:
            url: The case URL (used as case_id)
            case_number: Case number containing "IMM-"
            title: Case title
            court: Court name
            case_date: Case date
            html_content: Full HTML content

        Returns:
            Case: A validated Case instance
        """
        return cls(
            case_id=url,
            case_number=case_number,
            title=title,
            court=court,
            date=case_date,
            html_content=html_content,
        )

    @classmethod
    def generate_id(cls, case_number: str, title: str) -> str:
        """Generate a unique case ID from case number and title.

        Args:
            case_number: Case number
            title: Case title

        Returns:
            str: Generated unique ID
        """
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert case to dictionary for JSON export.

        Returns:
            dict: Case data as dictionary
        """
        return {
            "case_id": self.case_id,
            "case_number": self.case_number,
            "title": self.title,
            "court": self.court,
            "date": self.date.isoformat(),
            "html_content": self.html_content,
            "scraped_at": self.scraped_at.isoformat(),
        }

    def to_csv_row(self) -> list:
        """Convert case to CSV row format.

        Returns:
            list: Case data as CSV row
        """
        return [
            self.case_id,
            self.case_number,
            self.title,
            self.court,
            self.date.isoformat(),
            self.html_content,
            self.scraped_at.isoformat(),
        ]