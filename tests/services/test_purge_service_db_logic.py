from typing import List, Any
from src.services.purge_service import db_purge_year


class FakeCursor:
    def __init__(self, rows_map):
        # rows_map: dict[str, list]
        self.rows_map = rows_map
        self.description = None
        self._last_query = None
        self.rowcount = -1

    def execute(self, sql: str):
        self._last_query = sql.strip()
        # Simulate EXTRACT failure to force Python fallback
        if "EXTRACT(YEAR" in sql or "EXTRACT(YEAR FROM" in sql:
            raise Exception("SQL YEAR EXTRACT not supported")

        if sql.strip().lower().startswith("select * from cases limit 1"):
            # provide description columns
            self.description = [("id",), ("scraped_at",)]
            return

        if sql.strip().lower().startswith("select") and "from cases" in sql.lower():
            # return id + scraped values
            # expected format: SELECT id_col, scraped_col FROM cases
            self._last_result = self.rows_map.get("cases_rows", [])
            return

        # deletes
        if sql.strip().lower().startswith("delete from docket_entries"):
            # simulate rowcount
            self.rowcount = self.rows_map.get("deleted_docket_entries", 0)
            return

        if sql.strip().lower().startswith("delete from cases"):
            self.rowcount = self.rows_map.get("deleted_cases", 0)
            return

    def fetchall(self) -> List[Any]:
        # If last query was SELECT id_col, scraped_col FROM cases
        return self._last_result

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows_map):
        self.rows_map = rows_map
        self._cur = FakeCursor(rows_map)

    def cursor(self):
        return self._cur

    def commit(self):
        return

    def rollback(self):
        return


def test_db_purge_year_fallback_python_filter():
    # prepare rows: (id, scraped_at)
    rows = [("1", "2025-01-01"), ("2", "2025-02-02"), ("3", "2024-03-03")]
    rows_map = {
        "cases_rows": rows,
        "deleted_docket_entries": 4,
        "deleted_cases": 2,
    }

    def get_conn():
        return FakeConn(rows_map)

    res = db_purge_year(2025, get_conn, transactional=True, sql_year_filter=False)
    assert res["year"] == 2025
    # two cases in 2025
    assert res["cases_deleted"] == 2 or res["cases_deleted"] == -1
    assert res["docket_entries_deleted"] == 4
