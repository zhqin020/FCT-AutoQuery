from datetime import date


class DocketEntry:
    def __init__(self, doc_id, case_id, entry_date, entry_office, summary, id=None):
        self.doc_id = doc_id
        self.case_id = case_id
        self.entry_date = entry_date
        self.entry_office = entry_office
        self.summary = summary
        self.id = id

    def to_dict(self):
        return {
            "doc_id": self.doc_id,
            "case_id": self.case_id,
            "entry_date": (
                self.entry_date.isoformat()
                if isinstance(self.entry_date, date)
                else str(self.entry_date)
            ),
            "entry_office": self.entry_office,
            "summary": self.summary,
            "id": self.id,
        }


class FakeService:
    """A tiny fake service implementing a high-level fetch interface used by the
    CLI for integration testing. It avoids any browser automation.
    """

    def __init__(self, headless=True):
        self.headless = headless

    def fetch_case_and_docket(self, case_number: str, non_interactive: bool):
        # Return deterministic test data similar to what the real scraper yields.
        case_data = {
            "case_id": case_number,
            "case_type": "Test",
            "filing_date": date(2025, 1, 1),
            "office": "TestOffice",
            "style_of_cause": "Test v Test",
        }
        entries = [
            DocketEntry(
                doc_id=1,
                case_id=case_number,
                entry_date=date(2025, 1, 2),
                entry_office="TestOffice",
                summary="Test entry",
                id="1",
            )
        ]
        return case_data, entries

    def close(self):
        # nothing to close in the fake
        pass

    # Backwards-compatible method name if caller expects it
    def _extract_case_header(self, modal):
        return {
            "case_id": "IMM-12345-25",
            "case_type": "Test",
            "filing_date": date(2025, 1, 1),
            "office": "TestOffice",
            "style_of_cause": "Test v Test",
        }

    def _extract_docket_entries(self, modal, case_number):
        return [
            DocketEntry(
                doc_id=1,
                case_id=case_number,
                entry_date=date(2025, 1, 2),
                entry_office="TestOffice",
                summary="Test entry",
                id="1",
            )
        ]
