import sqlite3
from pathlib import Path

from src.services.purge_service import db_purge_year


def _create_test_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    # Create tables
    cur.execute(
        """
        CREATE TABLE cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_number TEXT,
            scraped_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE docket_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            content TEXT,
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    return conn


def test_db_purge_year_commits_and_deletes(tmp_path: Path):
    dbfile = tmp_path / "test.db"
    conn = _create_test_db(dbfile)
    cur = conn.cursor()
    # Insert two cases: 2022 and 2023
    cur.execute("INSERT INTO cases (case_number, scraped_at) VALUES (?, ?)", ("C1", "2022-05-01T00:00:00"))
    cur.execute("INSERT INTO cases (case_number, scraped_at) VALUES (?, ?)", ("C2", "2023-06-01T00:00:00"))
    conn.commit()
    # Get ids
    cur.execute("SELECT id FROM cases ORDER BY id")
    ids = [r[0] for r in cur.fetchall()]
    id_2022, id_2023 = ids
    # Add docket entries for both
    cur.execute("INSERT INTO docket_entries (case_id, content) VALUES (?, ?)", (id_2022, "x"))
    cur.execute("INSERT INTO docket_entries (case_id, content) VALUES (?, ?)", (id_2023, "y"))
    conn.commit()

    # Act: purge year 2023
    def get_conn():
        return conn

    res = db_purge_year(2023, get_conn, transactional=True)

    # Assert: only case 2023 and its docket entry removed
    assert res["year"] == 2023
    assert id_2023 in res["candidate_case_ids"]
    assert res["cases_deleted"] == 1
    assert res["docket_entries_deleted"] == 1

    # Confirm DB state: remaining case is 2022
    cur.execute("SELECT scraped_at FROM cases")
    remaining = [r[0] for r in cur.fetchall()]
    assert any("2022" in r for r in remaining)

    conn.close()
