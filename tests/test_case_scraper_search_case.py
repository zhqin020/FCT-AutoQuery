from src.services.case_scraper_service import CaseScraperService


class FakeInput:
    def __init__(self):
        self.value = ""

    def clear(self):
        self.value = ""

    def send_keys(self, text):
        self.value = text


class FakeDriver:
    def __init__(self, *, present_no_data=False, present_case=False, case_input=True):
        self.present_no_data = present_no_data
        self.present_case = present_case
        self.case_input = case_input
        self.page_source = "<html></html>"
        self.current_url = "https://example.test"
        self.last_get = None

    def find_elements(self, by, selector):
        # No data marker
        if isinstance(selector, str) and "No data available" in selector:
            return [1] if self.present_no_data else []

        # Case cell detection
        if isinstance(selector, str) and "contains(normalize-space(.)," in selector:
            return [1] if self.present_case else []

        # generic table row presence
        if isinstance(selector, str) and selector.endswith("//tbody//tr"):
            return [1] if self.present_case else []

        return []

    def find_element(self, by, selector=None):
        # Support being called either as find_element(by, selector) or
        # find_element((by, selector)) as used by expected_conditions helpers.
        if selector is None and isinstance(by, tuple):
            locator = by
            by, selector = locator[0], locator[1]

        # If asked for an input id, and our driver is configured to provide it,
        # return a FakeInput instance
        if selector in ("courtNumber", "selectCourtNumber", "selectRetcaseCourtNumber", "searchd") and self.case_input:
            return FakeInput()

        # Simulate tab02Submit missing by default
        raise Exception("not found")

    def execute_script(self, script, *args, **kwargs):
        return None

    def save_screenshot(self, p):
        return False

    def quit(self):
        return None

    def get(self, url):
        self.last_get = url


def _patch_wait(monkeypatch, svc):
    import src.services.case_scraper_service as css_mod

    class DummyWait:
        def __init__(self, drv, timeout):
            self._drv = drv

        def until(self, method):
            # Call the provided predicate with the driver; the predicate will
            # in turn call driver.find_element/locator, so our FakeDriver
            # should handle locator tuples.
            return method(self._drv)

    monkeypatch.setattr(css_mod, "WebDriverWait", DummyWait)


def test_search_case_no_results(monkeypatch):
    svc = CaseScraperService(headless=True)
    drv = FakeDriver(present_no_data=True, present_case=False)
    monkeypatch.setattr(svc, "_get_driver", lambda: drv)
    monkeypatch.setattr(svc, "initialize_page", lambda: None)
    svc._initialized = True
    svc.rate_limiter.wait_if_needed = lambda: None
    _patch_wait(monkeypatch, svc)

    found = svc.search_case("IMM-000-25")
    assert found is False


def test_search_case_found_immediate(monkeypatch):
    svc = CaseScraperService(headless=True)
    drv = FakeDriver(present_no_data=False, present_case=True)
    monkeypatch.setattr(svc, "_get_driver", lambda: drv)
    monkeypatch.setattr(svc, "initialize_page", lambda: None)
    svc._initialized = True
    svc.rate_limiter.wait_if_needed = lambda: None
    _patch_wait(monkeypatch, svc)

    # Ensure submit helper is no-op so flow proceeds to polling
    monkeypatch.setattr(svc, "_submit_search", lambda d, e: None)

    found = svc.search_case("IMM-123-25")
    assert found is True


def test_search_case_retry_then_found(monkeypatch):
    svc = CaseScraperService(headless=True)
    # First driver lacks case input and has no results; after initialize_page is called,
    # the driver returned will have present_case True
    drv1 = FakeDriver(present_no_data=False, present_case=False, case_input=False)
    drv2 = FakeDriver(present_no_data=False, present_case=True, case_input=True)

    # svc._get_driver should return drv1 initially, then drv2 after initialize_page
    sequence = {"called": 0}

    def get_driver_seq():
        if sequence["called"] == 0:
            return drv1
        return drv2

    monkeypatch.setattr(svc, "_get_driver", get_driver_seq)
    svc.rate_limiter.wait_if_needed = lambda: None

    # initialize_page will increment the sequence so subsequent _get_driver returns drv2
    def fake_init():
        sequence["called"] += 1

    monkeypatch.setattr(svc, "initialize_page", fake_init)
    _patch_wait(monkeypatch, svc)
    monkeypatch.setattr(svc, "_submit_search", lambda d, e: None)

    found = svc.search_case("IMM-999-25")
    assert found is True
