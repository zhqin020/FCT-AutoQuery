"""Case data model for Federal Court scraper."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Case:
    """Represents a scraped public case.

    Attributes:
        url: URL of the case
        court_file_no: Court File No. (e.g., IMM-12345-25)
        case_type: Type (e.g., Immigration Matters)
        type_of_action: Type of Action
        nature_of_proceeding: Nature of Proceeding (long text)
        filing_date: Filing Date
        office: Office (e.g., Toronto)
        style_of_cause: Style of Cause (long text, parties)
        language: Language
        html_content: Full HTML content
        scraped_at: When data was collected
    """

    url: str
    court_file_no: str
    case_type: Optional[str] = None
    type_of_action: Optional[str] = None
    nature_of_proceeding: Optional[str] = None
    filing_date: Optional[date] = None
    office: Optional[str] = None
    style_of_cause: Optional[str] = None
    language: Optional[str] = None
    html_content: str = ""
    scraped_at: datetime = field(default_factory=lambda: datetime.now())

    def __post_init__(self) -> None:
        """Validate the case data after initialization."""
        self._validate()

    def _validate(self) -> None:
        """Validate case data according to business rules."""
        if not self.url or not self.url.strip():
            raise ValueError("URL cannot be empty")

        if not self.court_file_no or not self.court_file_no.strip():
            raise ValueError("Court file number cannot be empty")

        if "IMM-" not in self.court_file_no:
            raise ValueError(
                f"Court file number must contain 'IMM-', got: {self.court_file_no}"
            )

        if not self.html_content or not self.html_content.strip():
            raise ValueError("HTML content cannot be empty")

        # HTML content cannot be whitespace only
        if not self.html_content.strip():
            raise ValueError("HTML content cannot be empty")

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
        """Create a Case instance from URL and data.

        Args:
            url: The case URL
            case_number: The court file number
            title: Case title
            court: Court name
            case_date: Case date
            html_content: HTML content

        Returns:
            Case: A validated Case instance
        """
        return cls(
            url=url,
            court_file_no=case_number,
            case_title=title,
            court_name=court,
            case_date=case_date,
            html_content=html_content,
        )

    @classmethod
    def generate_id(cls, case_number: str, title: str) -> str:
        """Generate a unique ID for the case.

        Args:
            case_number: The court file number
            title: Case title

        Returns:
            str: Generated ID
        """
        # Simple ID generation based on case number and title
        return f"{case_number}-{hash(title) % 10000}"

    def to_dict(self) -> dict:
        """Convert case to dictionary for JSON export.

        Returns:
            dict: Case data as dictionary
        """
        return {
            "case_id": self.url,
            "court_file_no": self.court_file_no,
            "case_title": self.case_title,
            "court_name": self.court_name,
            "case_date": self.case_date.isoformat(),
            "html_content": self.html_content,
            "scraped_at": self.scraped_at.isoformat(),
        }

    def to_csv_row(self) -> list:
        """Convert case to CSV row format.

        Returns:
            list: Case data as CSV row
        """
        return [
            self.url,
            self.court_file_no,
            self.case_title,
            self.court_name,
            self.case_date.isoformat(),
            self.html_content,
            self.scraped_at.isoformat(),
        ]
