"""Contract tests for data export formats."""

import json
from datetime import date, datetime
from src.models.case import Case


class TestDataExportFormats:
    """Contract tests for data export functionality."""

    def test_case_to_dict_export(self):
        """Test Case.to_dict() produces correct JSON-serializable format."""
        # Create a test case
        case = Case(
            case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22",
            case_number="IMM-12345-22",
            title="Test Immigration Case",
            court="Federal Court",
            date=date(2023, 6, 15),
            html_content="<html><body>Test content</body></html>",
            scraped_at=datetime(2023, 6, 15, 10, 30, 0),
        )

        # Convert to dict
        case_dict = case.to_dict()

        # Verify structure
        assert isinstance(case_dict, dict)
        assert "case_id" in case_dict
        assert "case_number" in case_dict
        assert "title" in case_dict
        assert "court" in case_dict
        assert "date" in case_dict
        assert "html_content" in case_dict
        assert "scraped_at" in case_dict

        # Verify values
        assert case_dict["case_id"] == "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"
        assert case_dict["case_number"] == "IMM-12345-22"
        assert case_dict["title"] == "Test Immigration Case"
        assert case_dict["court"] == "Federal Court"
        assert case_dict["date"] == "2023-06-15"
        assert case_dict["html_content"] == "<html><body>Test content</body></html>"
        assert case_dict["scraped_at"] == "2023-06-15T10:30:00"

        # Verify JSON serializable
        json_str = json.dumps(case_dict)
        assert json_str is not None
        assert len(json_str) > 0

        # Verify round-trip
        parsed = json.loads(json_str)
        assert parsed == case_dict

    def test_case_to_csv_row_export(self):
        """Test Case.to_csv_row() produces correct CSV row format."""
        # Create a test case
        case = Case(
            case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-67890-23",
            case_number="IMM-67890-23",
            title="Another Test Case",
            court="Federal Court",
            date=date(2023, 7, 20),
            html_content="<html><body>Another test</body></html>",
            scraped_at=datetime(2023, 7, 20, 14, 45, 30),
        )

        # Convert to CSV row
        csv_row = case.to_csv_row()

        # Verify it's a list
        assert isinstance(csv_row, list)
        assert len(csv_row) == 7  # Should have 7 columns

        # Verify values
        assert csv_row[0] == "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-67890-23"
        assert csv_row[1] == "IMM-67890-23"
        assert csv_row[2] == "Another Test Case"
        assert csv_row[3] == "Federal Court"
        assert csv_row[4] == "2023-07-20"
        assert csv_row[5] == "<html><body>Another test</body></html>"
        assert csv_row[6] == "2023-07-20T14:45:30"

    def test_case_export_with_special_characters(self):
        """Test export handles special characters correctly."""
        # Create case with special characters
        case = Case(
            case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-99999-24",
            case_number="IMM-99999-24",
            title="Test Case with spécial caractères: éñü",
            court="Federal Court",
            date=date(2023, 8, 10),
            html_content='<html><body>Content with "quotes" and \'apostrophes\'</body></html>',
            scraped_at=datetime(2023, 8, 10, 9, 15, 0),
        )

        # Test dict export
        case_dict = case.to_dict()
        json_str = json.dumps(case_dict, ensure_ascii=False)
        assert "spécial caractères" in json_str

        # Test CSV export
        csv_row = case.to_csv_row()
        assert "spécial caractères" in csv_row[2]  # title
        assert '"quotes"' in csv_row[5]  # html_content

    def test_case_export_with_empty_fields(self):
        """Test export handles empty/minimal fields correctly."""
        # Create minimal case with valid HTML content
        case = Case(
            case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-00000-25",
            case_number="IMM-00000-25",
            title="",  # Empty title is allowed
            court="Federal Court",
            date=date.today(),
            html_content="<html></html>",  # Minimal valid HTML
            scraped_at=datetime.now(),
        )

        # Should not raise exceptions
        case_dict = case.to_dict()
        assert case_dict["title"] == ""
        assert case_dict["html_content"] == "<html></html>"

        csv_row = case.to_csv_row()
        assert csv_row[2] == ""  # title
        assert csv_row[5] == "<html></html>"  # html_content

    def test_case_dict_json_schema_compliance(self):
        """Test that Case.to_dict() complies with the JSON schema."""
        case = Case(
            case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-11111-26",
            case_number="IMM-11111-26",
            title="Schema Compliance Test",
            court="Federal Court",
            date=date(2023, 9, 5),
            html_content="<html><body>Test</body></html>",
            scraped_at=datetime(2023, 9, 5, 11, 0, 0),
        )

        case_dict = case.to_dict()

        # Check required fields are present
        required_fields = ["case_id", "case_number", "title", "court", "date", "html_content", "scraped_at"]
        for field in required_fields:
            assert field in case_dict
            assert case_dict[field] is not None

        # Check case_number contains IMM-
        assert "IMM-" in case_dict["case_number"]

        # Check html_content is not empty
        assert len(case_dict["html_content"]) > 0

        # Check date formats are ISO strings
        assert isinstance(case_dict["date"], str)
        assert isinstance(case_dict["scraped_at"], str)