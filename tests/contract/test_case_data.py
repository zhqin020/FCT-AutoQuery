"""Contract tests for case data validation."""

import pytest
from datetime import date
from src.models.case import Case


class TestCaseDataContract:
    """Contract tests for Case data model."""

    def test_case_creation_with_valid_data(self, sample_case_data):
        """Test that Case can be created with valid data."""
        case = Case(**sample_case_data)
        assert case.case_id == sample_case_data["case_id"]
        assert case.case_number == sample_case_data["case_number"]
        assert case.title == sample_case_data["title"]
        assert case.court == sample_case_data["court"]
        assert case.date == sample_case_data["date"]
        assert case.html_content == sample_case_data["html_content"]

    def test_case_validation_requires_imm_in_case_number(self, sample_case_data):
        """Test that case number must contain IMM-."""
        invalid_data = sample_case_data.copy()
        invalid_data["case_number"] = "ABC-12345-22"  # No IMM-

        with pytest.raises(ValueError, match="Case number must contain 'IMM-'"):
            Case(**invalid_data)

    def test_case_validation_requires_non_empty_html_content(self, sample_case_data):
        """Test that HTML content cannot be empty."""
        invalid_data = sample_case_data.copy()
        invalid_data["html_content"] = ""

        with pytest.raises(ValueError, match="HTML content cannot be empty"):
            Case(**invalid_data)

    def test_case_validation_requires_non_empty_html_content_whitespace_only(self, sample_case_data):
        """Test that HTML content cannot be whitespace only."""
        invalid_data = sample_case_data.copy()
        invalid_data["html_content"] = "   \n\t   "

        with pytest.raises(ValueError, match="HTML content cannot be empty"):
            Case(**invalid_data)

    def test_case_validation_requires_non_empty_case_id(self, sample_case_data):
        """Test that case ID cannot be empty."""
        invalid_data = sample_case_data.copy()
        invalid_data["case_id"] = ""

        with pytest.raises(ValueError, match="Case ID cannot be empty"):
            Case(**invalid_data)

    def test_case_to_dict_conversion(self, sample_case_data):
        """Test conversion to dictionary format."""
        case = Case(**sample_case_data)
        result = case.to_dict()

        assert isinstance(result, dict)
        assert result["case_id"] == sample_case_data["case_id"]
        assert result["case_number"] == sample_case_data["case_number"]
        assert result["title"] == sample_case_data["title"]
        assert result["court"] == sample_case_data["court"]
        assert result["date"] == sample_case_data["date"].isoformat()
        assert result["html_content"] == sample_case_data["html_content"]
        assert "scraped_at" in result

    def test_case_to_csv_row_conversion(self, sample_case_data):
        """Test conversion to CSV row format."""
        case = Case(**sample_case_data)
        result = case.to_csv_row()

        assert isinstance(result, list)
        assert len(result) == 7  # 7 fields
        assert result[0] == sample_case_data["case_id"]
        assert result[1] == sample_case_data["case_number"]
        assert result[2] == sample_case_data["title"]
        assert result[3] == sample_case_data["court"]
        assert result[4] == sample_case_data["date"].isoformat()
        assert result[5] == sample_case_data["html_content"]

    def test_case_from_url_factory_method(self, sample_case_url):
        """Test creating Case from URL using factory method."""
        case = Case.from_url(
            url=sample_case_url,
            case_number="IMM-12345-22",
            title="Test Case",
            court="Federal Court",
            case_date=date(2023, 6, 15),
            html_content="<html>Test</html>"
        )

        assert case.case_id == sample_case_url
        assert case.case_number == "IMM-12345-22"
        assert case.title == "Test Case"
        assert case.court == "Federal Court"
        assert case.date == date(2023, 6, 15)
        assert case.html_content == "<html>Test</html>"

    def test_case_generate_id_method(self):
        """Test ID generation method."""
        case_id = Case.generate_id("IMM-12345-22", "Test Case")
        assert isinstance(case_id, str)
        assert len(case_id) == 36  # UUID length