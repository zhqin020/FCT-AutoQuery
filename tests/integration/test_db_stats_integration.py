from datetime import datetime

import psycopg2
import pytest

from src.lib.config import Config
from src.services.url_discovery_service import UrlDiscoveryService


def test_get_processing_stats_integration():
    """Integration test: insert a sample case, call get_processing_stats, then clean up."""
    db_config = Config.get_db_config()

    try:
        conn = psycopg2.connect(**db_config)
    except Exception as e:  # pragma: no cover - integration skip
        pytest.skip(f"Database not available: {e}")

    cursor = conn.cursor()

    court_id = "IMM-99999-25"
    now = datetime.now()

    try:
        # Insert or upsert a test case
        cursor.execute(
            """
            INSERT INTO cases (court_file_no, case_type, type_of_action, nature_of_proceeding, filing_date, office, style_of_cause, language, html_content, scraped_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (court_file_no) DO UPDATE SET scraped_at = EXCLUDED.scraped_at
        """,
            (
                court_id,
                "IntegrationTest",
                "TestAction",
                "Nature",
                "2025-01-01",
                "TestOffice",
                "A v B",
                "EN",
                "<html>test</html>",
                now,
            ),
        )
        conn.commit()

        svc = UrlDiscoveryService(Config)
        stats = svc.get_processing_stats(2025)

        assert isinstance(stats, dict)
        assert stats["year"] == 2025
        assert stats["total_cases"] >= 1
        assert stats["last_scraped"] is not None

    finally:
        # Clean up inserted test data
        cursor.execute(
            "DELETE FROM docket_entries WHERE court_file_no = %s", (court_id,)
        )
        cursor.execute("DELETE FROM cases WHERE court_file_no = %s", (court_id,))
        conn.commit()
        cursor.close()
        conn.close()
