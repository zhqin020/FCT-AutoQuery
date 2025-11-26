import time

from src.services.case_scraper_service import CaseScraperService


class FakeElement:
    def __init__(self):
        pass


class FakeDriver:
    def __init__(self, present_case=False):
        # present_case controls whether table lookup finds the case
        self.present_case = present_case
        self.current_window_handle = "window-1"

    def find_element(self, by, value):
        # Return a generic element for input lookups
        return FakeElement()

    def find_elements(self, by, value):
        # If searching for the case number row, simulate found/not found
        if isinstance(value, str) and value.startswith("//table//td"):
            return [object()] if self.present_case else []
        if isinstance(value, str) and "No data available" in value:
            return []
        return []

    def execute_script(self, script, *args, **kwargs):
        return None

    def get(self, url):
        return None


class FakeWait:
    def __init__(self, driver, timeout):
        self.driver = driver

    def until(self, condition):
        # Call the condition with our fake driver; many selenium expected
        # conditions are callables accepting driver
        return condition(self.driver)


def test_search_uses_cached_input_and_reuses_session(monkeypatch):
    svc = CaseScraperService(headless=True)

    # Provide a fake driver that will report the case present
    fake = FakeDriver(present_case=True)

    # Ensure _get_driver returns our fake driver
    monkeypatch.setattr(svc, "_get_driver", lambda: fake)

    # Make WebDriverWait use the FakeWait which just calls the condition
    monkeypatch.setattr("src.services.case_scraper_service.WebDriverWait", FakeWait)

    # Prevent initialize_page from actually performing any network ops
    monkeypatch.setattr(svc, "initialize_page", lambda: setattr(svc, "_initialized", True))

    # Simulate that a cached input id was discovered previously
    svc._initialized = True
    svc._found_case_input = "courtNumber"

    # First call should return True (present_case True)
    assert svc.search_case("IMM-FAKE-01") is True

    # Second call should also return True and should reuse same cached input
    assert svc.search_case("IMM-FAKE-01") is True


def test_get_driver_restarts_on_dead_driver(monkeypatch):
    svc = CaseScraperService(headless=True)

    # Create a "dead" driver which raises when accessing window handle
    class DeadDriver:
        @property
        def current_window_handle(self):
            raise RuntimeError("session gone")

    dead = DeadDriver()
    svc._driver = dead

    # Provide a new good driver via _setup_driver when restart occurs
    good = FakeDriver(present_case=False)
    monkeypatch.setattr(svc, "_setup_driver", lambda: good)

    # Call _get_driver; it should attempt restart and return the good driver
    driver = svc._get_driver()
    assert driver is good
    assert svc._initialized is False
