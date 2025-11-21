"""Integration tests for CSV/JSON export functionality."""

import json
import csv
import tempfile
import os
from datetime import date, datetime
from src.models.case import Case
from src.services.export_service import ExportService


class TestExportFormats:
    """Integration tests for CSV and JSON export functionality."""

    def test_export_service_import(self):
        """Test that ExportService can be imported."""
        assert ExportService is not None

    def test_case_list_to_json_export(self):
        """Test exporting multiple cases to JSON format."""
        # Create test cases
        cases = [
            Case(
                case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22",
                case_number="IMM-12345-22",
                title="Test Case 1",
                court="Federal Court",
                date=date(2023, 6, 15),
                html_content="<html><body>Case 1 content</body></html>",
                scraped_at=datetime(2023, 6, 15, 10, 0, 0),
            ),
            Case(
                case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-67890-23",
                case_number="IMM-67890-23",
                title="Test Case 2",
                court="Federal Court",
                date=date(2023, 7, 20),
                html_content="<html><body>Case 2 content</body></html>",
                scraped_at=datetime(2023, 7, 20, 11, 0, 0),
            ),
        ]

        # Convert to expected JSON structure
        expected_data = [case.to_dict() for case in cases]

        # Test JSON serialization
        json_str = json.dumps(expected_data, indent=2, ensure_ascii=False)
        assert json_str is not None
        assert len(json_str) > 0

        # Test round-trip
        parsed_data = json.loads(json_str)
        assert len(parsed_data) == 2
        assert parsed_data[0]["case_number"] == "IMM-12345-22"
        assert parsed_data[1]["case_number"] == "IMM-67890-23"

    def test_case_list_to_csv_export(self):
        """Test exporting multiple cases to CSV format."""
        # Create test cases
        cases = [
            Case(
                case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-11111-24",
                case_number="IMM-11111-24",
                title="CSV Test Case 1",
                court="Federal Court",
                date=date(2023, 8, 10),
                html_content="<html><body>CSV content 1</body></html>",
                scraped_at=datetime(2023, 8, 10, 9, 30, 0),
            ),
            Case(
                case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-22222-24",
                case_number="IMM-22222-24",
                title="CSV Test Case 2",
                court="Federal Court",
                date=date(2023, 9, 5),
                html_content="<html><body>CSV content 2</body></html>",
                scraped_at=datetime(2023, 9, 5, 14, 15, 0),
            ),
        ]

        # Test CSV row generation
        csv_rows = [case.to_csv_row() for case in cases]
        assert len(csv_rows) == 2
        assert len(csv_rows[0]) == 7  # 7 columns
        assert len(csv_rows[1]) == 7

        # Test CSV writing
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(["case_id", "case_number", "title", "court", "date", "html_content", "scraped_at"])
            # Write data
            writer.writerows(csv_rows)
            temp_file = f.name

        try:
            # Verify file was written
            assert os.path.exists(temp_file)
            with open(temp_file, 'r') as f:
                content = f.read()
                assert "IMM-11111-24" in content
                assert "IMM-22222-24" in content
                assert "CSV Test Case 1" in content
        finally:
            os.unlink(temp_file)

    def test_export_with_special_characters_csv(self):
        """Test CSV export handles special characters correctly."""
        case = Case(
            case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-33333-25",
            case_number="IMM-33333-25",
            title="Case with spécial chars: éñü",
            court="Federal Court",
            date=date(2023, 10, 1),
            html_content='<html><body>Content with "quotes" and commas, and newlines\n</body></html>',
            scraped_at=datetime(2023, 10, 1, 12, 0, 0),
        )

        csv_row = case.to_csv_row()

        # Test CSV writing with special characters
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv', delete=False, encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["case_id", "case_number", "title", "court", "date", "html_content", "scraped_at"])
            writer.writerow(csv_row)
            temp_file = f.name

        try:
            with open(temp_file, 'r', encoding='utf-8') as f:
                content = f.read()
                assert "spécial chars" in content
                assert '"quotes"' in content
                assert "commas" in content
        finally:
            os.unlink(temp_file)

    def test_export_empty_case_list(self):
        """Test export handles empty case lists."""
        cases = []

        # Should handle empty lists gracefully
        json_str = json.dumps([case.to_dict() for case in cases])
        assert json_str == "[]"

        # CSV with empty data
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(["case_id", "case_number", "title", "court", "date", "html_content", "scraped_at"])
            # No data rows
            temp_file = f.name

        try:
            with open(temp_file, 'r') as f:
                content = f.read()
                lines = content.strip().split('\n')
                assert len(lines) == 1  # Just header
                assert "case_id" in lines[0]
        finally:
            os.unlink(temp_file)

    def test_export_file_creation(self):
        """Test that export files are created with correct names."""
        cases = [
            Case(
                case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-44444-25",
                case_number="IMM-44444-25",
                title="File Creation Test",
                court="Federal Court",
                date=date(2023, 11, 1),
                html_content="<html><body>Test</body></html>",
                scraped_at=datetime(2023, 11, 1, 13, 0, 0),
            ),
        ]

        # Test JSON file creation
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as json_file:
            json_file_path = json_file.name

        try:
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump([case.to_dict() for case in cases], f, indent=2, ensure_ascii=False)

            assert os.path.exists(json_file_path)
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                assert len(data) == 1
                assert data[0]["case_number"] == "IMM-44444-25"
        finally:
            os.unlink(json_file_path)

        # Test CSV file creation
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as csv_file:
            csv_file_path = csv_file.name

        try:
            with open(csv_file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["case_id", "case_number", "title", "court", "date", "html_content", "scraped_at"])
                for case in cases:
                    writer.writerow(case.to_csv_row())

            assert os.path.exists(csv_file_path)
            with open(csv_file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
                assert len(rows) == 2  # Header + 1 data row
                assert rows[1][1] == "IMM-44444-25"  # case_number column
        finally:
            os.unlink(csv_file_path)

    def test_export_service_json_export(self):
        """Test ExportService JSON export functionality."""
        # Create test cases
        cases = [
            Case(
                case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-55555-25",
                case_number="IMM-55555-25",
                title="ExportService JSON Test",
                court="Federal Court",
                date=date(2023, 12, 1),
                html_content="<html><body>ExportService test content</body></html>",
                scraped_at=datetime(2023, 12, 1, 14, 0, 0),
            ),
        ]

        # Create ExportService with temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            export_service = ExportService(temp_dir)

            # Export to JSON
            json_path = export_service.export_to_json(cases, "test_export.json")

            # Verify file was created
            assert os.path.exists(json_path)

            # Verify content
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                assert len(data) == 1
                assert data[0]["case_number"] == "IMM-55555-25"
                assert data[0]["title"] == "ExportService JSON Test"

    def test_export_service_csv_export(self):
        """Test ExportService CSV export functionality."""
        # Create test cases
        cases = [
            Case(
                case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-66666-25",
                case_number="IMM-66666-25",
                title="ExportService CSV Test",
                court="Federal Court",
                date=date(2023, 12, 15),
                html_content="<html><body>CSV export test</body></html>",
                scraped_at=datetime(2023, 12, 15, 15, 0, 0),
            ),
        ]

        # Create ExportService with temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            export_service = ExportService(temp_dir)

            # Export to CSV
            csv_path = export_service.export_to_csv(cases, "test_export.csv")

            # Verify file was created
            assert os.path.exists(csv_path)

            # Verify content
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
                assert len(rows) == 2  # Header + 1 data row
                assert rows[1][1] == "IMM-66666-25"  # case_number
                assert rows[1][2] == "ExportService CSV Test"  # title

    def test_export_service_both_formats(self):
        """Test ExportService exporting to both JSON and CSV formats."""
        # Create test cases
        cases = [
            Case(
                case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-77777-25",
                case_number="IMM-77777-25",
                title="Both Formats Test",
                court="Federal Court",
                date=date(2024, 1, 1),
                html_content="<html><body>Both formats test</body></html>",
                scraped_at=datetime(2024, 1, 1, 16, 0, 0),
            ),
        ]

        # Create ExportService with temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            export_service = ExportService(temp_dir)

            # Export to both formats
            result = export_service.export_all_formats(cases, "both_formats_test")

            # Verify both files were created
            assert "json" in result
            assert "csv" in result
            assert os.path.exists(result["json"])
            assert os.path.exists(result["csv"])

            # Verify JSON content
            with open(result["json"], 'r', encoding='utf-8') as f:
                json_data = json.load(f)
                assert len(json_data) == 1
                assert json_data[0]["case_number"] == "IMM-77777-25"

            # Verify CSV content
            with open(result["csv"], 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
                assert len(rows) == 2
                assert rows[1][1] == "IMM-77777-25"

    def test_export_service_validation(self):
        """Test ExportService validation of cases."""
        # Create ExportService with temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            export_service = ExportService(temp_dir)

            # Test empty cases list
            try:
                export_service.export_to_json([])
                assert False, "Should have raised ValueError for empty list"
            except ValueError as e:
                assert "empty case list" in str(e)

            # Test with non-Case objects (this should fail validation)
            try:
                export_service.export_to_json(["not a case object"])
                assert False, "Should have raised ValueError for invalid objects"
            except ValueError as e:
                assert "not a Case instance" in str(e)

    def test_export_service_special_characters(self):
        """Test ExportService handles special characters correctly."""
        # Create test case with special characters
        cases = [
            Case(
                case_id="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-99999-25",
                case_number="IMM-99999-25",
                title="Spécial caractères: éñü 测试",
                court="Federal Court",
                date=date(2024, 2, 1),
                html_content='<html><body>Content with "quotes", commas, and newlines\n测试</body></html>',
                scraped_at=datetime(2024, 2, 1, 18, 0, 0),
            ),
        ]

        # Create ExportService with temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            export_service = ExportService(temp_dir)

            # Export to both formats
            result = export_service.export_all_formats(cases, "special_chars_test")

            # Verify JSON preserves special characters
            with open(result["json"], 'r', encoding='utf-8') as f:
                json_data = json.load(f)
                assert "Spécial caractères" in json_data[0]["title"]
                assert "测试" in json_data[0]["html_content"]

            # Verify CSV preserves special characters
            with open(result["csv"], 'r', encoding='utf-8') as f:
                content = f.read()
                assert "Spécial caractères" in content
                assert "测试" in content