import xml.etree.ElementTree as ET
import time

from src.services.case_scraper_service import CaseScraperService


class ClickableElement:
    def __init__(self, text=""):
        self.text = text
        self.clicked = False

    def click(self):
        self.clicked = True


class FakeDriver:
    def __init__(self, els=None, raise_on_execute=False):
        # els: list to return from find_elements
        self._els = els or []
        self.raise_on_execute = raise_on_execute
        self.executed = []

    def find_elements(self, by, xp):
        # ignore xpath content for tests; return configured elements
        return self._els

    def execute_script(self, script, *args):
        self.executed.append((script, args))
        if self.raise_on_execute:
            raise RuntimeError("execute_script forced failure")


def test_dismiss_cookie_banner_uses_js_click_when_available(monkeypatch):
    el = ClickableElement(text="Accept")
    drv = FakeDriver(els=[el], raise_on_execute=False)
    svc = CaseScraperService(headless=True)

    # Monkeypatch sleep to avoid delays in tests
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    # Should not raise
    svc._dismiss_cookie_banner(drv)

    # JS click should have been attempted and recorded
    assert len(drv.executed) >= 1
    script, args = drv.executed[0]
    assert "click" in script


def test_dismiss_cookie_banner_falls_back_to_native_click(monkeypatch):
    el = ClickableElement(text="I agree")
    # driver will raise on execute_script, causing native click to be invoked
    drv = FakeDriver(els=[el], raise_on_execute=True)
    svc = CaseScraperService(headless=True)

    monkeypatch.setattr(time, "sleep", lambda *_: None)

    svc._dismiss_cookie_banner(drv)

    # execute_script was attempted (and raised), and native click should set flag
    assert len(drv.executed) >= 1
    assert el.clicked is True


def test_dismiss_cookie_banner_no_elements_no_error(monkeypatch):
    drv = FakeDriver(els=[])
    svc = CaseScraperService(headless=True)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    # Should return without raising
    svc._dismiss_cookie_banner(drv)

    assert len(drv.executed) == 0
