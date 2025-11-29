import xml.etree.ElementTree as ET

from src.services.case_scraper_service import CaseScraperService
from tests.utils.fake_webelement import FakeWebElement


class SimpleElement:
    def __init__(self):
        self.clicked = False

    def click(self):
        self.clicked = True


class FakeDriver:
    def __init__(self):
        self.last_get = None
        self.page_source = "<html></html>"
        self.current_url = "https://example.test"

    def get(self, url):
        self.last_get = url

    def execute_script(self, script, *args, **kwargs):
        return None

    def quit(self):
        return None

    def save_screenshot(self, p):
        return False


class SeqWait:
    """A WebDriverWait stand-in that returns pre-set responses in sequence.

    Construct with a list of values to return for each `until` call. If a
    value is an Exception instance, `until` will raise it.
    """

    def __init__(self, drv, timeout, responses=None):
        self._drv = drv
        # responses will be injected by test via attribute on driver
        self._responses = responses if responses is not None else []

    def until(self, method):
        if not self._responses:
            # default: call the method with driver
            return method(self._drv)
        next_val = self._responses.pop(0)
        if isinstance(next_val, Exception):
            raise next_val
        return next_val


def test_initialize_page_happy_path(monkeypatch):
    svc = CaseScraperService(headless=True)
    drv = FakeDriver()

    # responses: body present, clickable search tab, presence of case input id
    responses = [True, SimpleElement(), True]

    # Monkeypatch WebDriverWait factory to return SeqWait with our responses
    import src.services.case_scraper_service as css_mod

    def fake_wait_factory(d, timeout):
        w = SeqWait(d, timeout, responses=list(responses))
        return w

    monkeypatch.setattr(css_mod, "WebDriverWait", fake_wait_factory)

    # Monkeypatch svc._get_driver to return our fake driver and _dismiss_cookie_banner to no-op
    monkeypatch.setattr(svc, "_get_driver", lambda: drv)
    monkeypatch.setattr(svc, "_dismiss_cookie_banner", lambda d: None)

    # Also monkeypatch presence_of_element_located to be simple truthy when called
    # But we already return True from SeqWait for that call

    # Run initialize_page
    svc.initialize_page()

    # After successful init, service should have _initialized True
    assert getattr(svc, "_initialized", False) is True


def test_initialize_page_fallback_to_generic(monkeypatch):
    svc = CaseScraperService(headless=True)
    drv = FakeDriver()

    # Simulate: first until (body presence) raises an exception to trigger fallback,
    # then the fallback wait for searchd returns True. Use a shared list so
    # sequential SeqWait instances consume the same responses.
    seq = [Exception("load failed"), True]

    import src.services.case_scraper_service as css_mod

    def fake_wait_factory(d, timeout):
        w = SeqWait(d, timeout, responses=seq)
        return w

    monkeypatch.setattr(css_mod, "WebDriverWait", fake_wait_factory)

    monkeypatch.setattr(svc, "_get_driver", lambda: drv)
    # no-op cookie dismissal
    monkeypatch.setattr(svc, "_dismiss_cookie_banner", lambda d: None)

    svc.initialize_page()

    # Fallback should set generic mode and initialized flag
    assert getattr(svc, "_initialized", False) is True
    assert getattr(svc, "_search_mode", "") == "generic"
    # driver should have been navigated to fallback URL
    assert drv.last_get is not None and "/search" in drv.last_get
