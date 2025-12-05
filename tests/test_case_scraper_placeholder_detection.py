from types import SimpleNamespace
from src.services.case_scraper_service import CaseScraperService


class FakeTable:
    def __init__(self, headers=None, rows=None, placeholder=False):
        self.headers = headers or []
        self.rows = rows or []
        self.placeholder = placeholder

    def find_elements(self, by, selector):
        # For header requests
        if selector == ".//th":
            return [SimpleNamespace(text=h) for h in self.headers]
        # For td placeholder XPath inside this table
        if selector.startswith(".//td[") and self.placeholder:
            return [SimpleNamespace(text='No data available')]
        # For searching case number inside this table
        if selector.startswith(".//td[contains(normalize-space(.),"):
            # Extract the substring searched for inside the XPATH
            import re
            m = re.search(r"contains\(normalize-space\(\.\), '(.+?)'\)", selector)
            if m:
                substr = m.group(1)
            else:
                substr = None
            if substr and self.rows:
                return [SimpleNamespace(text=r) for r in self.rows if substr in r]
            return []
            return []
        # For tbody row counts
        if selector == ".//tbody//tr":
            return [SimpleNamespace(text=r) for r in self.rows]
        return []


class FakeDriverMulti:
    def __init__(self, table_a: FakeTable, table_b: FakeTable):
        self.table_a = table_a
        self.table_b = table_b

    def find_elements(self, by, selector):
        # When asked for tables, return objects that support find_elements
        if selector == "//table":
            return [self.table_a, self.table_b]
        # fallback: other generic selectors used by code; return based on both tables
        if selector.endswith("//tbody//tr"):
            # combine rows from both tables
            rows = []
            rows.extend(self.table_a.rows)
            rows.extend(self.table_b.rows)
            return [SimpleNamespace(text=r) for r in rows]
        # placeholder detection across all tables
        if "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'" in selector:
            # return placeholder elements in either table
            res = []
            if self.table_a.placeholder:
                res.append(SimpleNamespace(text='No data available'))
            if self.table_b.placeholder:
                res.append(SimpleNamespace(text='No data available'))
            return res
        # td case matches across tables
        if "contains(normalize-space(.)," in selector:
            substr = selector.split("contains(normalize-space(.), '")[-1].split("')")[0]
            res = []
            for r in self.table_a.rows + self.table_b.rows:
                if substr in r:
                    res.append(SimpleNamespace(text=r))
            return res
        return []

    def find_element(self, by, selector=None):
        # For input ids we can return a simple input-like object
        if selector in ("courtNumber", "selectCourtNumber", "selectRetcaseCourtNumber", "searchd"):
            return SimpleNamespace(get_attribute=lambda name: '')
        raise Exception("not found")

    def execute_script(self, *a, **k):
        return None

    def save_screenshot(self, p):
        return False

    def get(self, url):
        pass


def _patch_wait(monkeypatch, svc):
    import src.services.case_scraper_service as css_mod

    class DummyWait:
        def __init__(self, drv, timeout):
            self._drv = drv

        def until(self, method):
            return method(self._drv)

    monkeypatch.setattr(css_mod, "WebDriverWait", DummyWait)


def test_placeholder_in_other_table_does_not_hide_results(monkeypatch):
    svc = CaseScraperService(headless=True)
    # table A has 'no data available' placeholder but is not the results table
    table_a = FakeTable(headers=["Example"], rows=["Example row"], placeholder=True)
    # table B is the results table and contains a case row
    table_b = FakeTable(headers=["Court file", "Style"], rows=["IMM-3-21 HOANG NAM"], placeholder=False)
    drv = FakeDriverMulti(table_a, table_b)

    monkeypatch.setattr(svc, "_get_driver", lambda: drv)
    monkeypatch.setattr(svc, "initialize_page", lambda: None)
    svc._initialized = True
    svc.rate_limiter.wait_if_needed = lambda: None
    _patch_wait(monkeypatch, svc)
    monkeypatch.setattr(svc, "_submit_search", lambda d, e: None)

    found = svc.search_case("IMM-3-21")
    assert found is True
