import os
import pytest
from src.services.purge_service import db_purge_year


POSTGRES_DSN = os.environ.get("POSTGRES_TEST_DSN")


@pytest.mark.skip(reason="Skipping destructive DB purge test in this environment")
def test_db_purge_year_sql_path_postgres(POSTGRES_DSN=POSTGRES_DSN):
    """Integration test: run db_purge_year against Postgres to exercise SQL-year-filter.

    This test runs only when `POSTGRES_TEST_DSN` env var is provided and will
    create/cleanup a small test table set. It also requires `psycopg2` to be
    available in the test environment. The test is intentionally lightweight.
    """
    psycopg2 = pytest.importorskip("psycopg2")

    dsn = POSTGRES_DSN
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    try:
        # Create minimal schema
        cur.execute("CREATE TABLE IF NOT EXISTS cases (id SERIAL PRIMARY KEY, scraped_at TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS docket_entries (id SERIAL PRIMARY KEY, case_id INTEGER REFERENCES cases(id))")
        conn.commit()

        # Insert rows for two years
        cur.execute("INSERT INTO cases (scraped_at) VALUES (%s) RETURNING id", ("2023-01-02T00:00:00",))
        id1 = cur.fetchone()[0]
        cur.execute("INSERT INTO cases (scraped_at) VALUES (%s) RETURNING id", ("2024-01-02T00:00:00",))
        id2 = cur.fetchone()[0]
        cur.execute("INSERT INTO docket_entries (case_id) VALUES (%s)", (id1,))
        conn.commit()

        # Run purge with SQL filter forced on
        def get_conn():
            return psycopg2.connect(dsn)

        res = db_purge_year(2023, get_conn, transactional=True, sql_year_filter=True)
        assert res["year"] == 2023
        assert id1 in res["candidate_case_ids"]
        assert res["cases_deleted"] >= 1
    finally:
        # Cleanup test rows (best-effort)
        try:
            cur.execute("DELETE FROM docket_entries")
            cur.execute("DELETE FROM cases")
            conn.commit()
        except Exception:
            conn.rollback()
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
