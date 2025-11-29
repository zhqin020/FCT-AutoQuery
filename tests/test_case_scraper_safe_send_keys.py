import xml.etree.ElementTree as ET

from tests.utils.fake_webelement import FakeWebElement
from src.services.case_scraper_service import CaseScraperService


class NativeElement(FakeWebElement):
    def clear(self):
        # no-op clear
        self._cleared = True

    def send_keys(self, text: str):
        # record the sent text for assertions
        self._sent = text


class FakeDriver:
    def __init__(self):
        self.executed = []

    def execute_script(self, script: str, *args):
        # record the script and args so tests can assert fallback usage
        self.executed.append((script, args))


def test_safe_send_keys_uses_native_send_keys_when_available():
    el = ET.Element("input")
    native = NativeElement(el, el)
    svc = CaseScraperService(headless=True)
    # driver that would raise if fallback used (ensures native path used)
    class FailDriver(FakeDriver):
        def execute_script(self, script: str, *args):
            raise RuntimeError("JS fallback should not be invoked in native path")

    drv = FailDriver()

    svc._safe_send_keys(drv, native, "IMM-1-25")
    assert getattr(native, "_sent", None) == "IMM-1-25"


def test_safe_send_keys_uses_js_fallback_when_send_keys_missing():
    # Use minimal FakeWebElement which does not implement send_keys
    el = ET.Element("input")
    fake_el = FakeWebElement(el, el)
    svc = CaseScraperService(headless=True)
    drv = FakeDriver()

    # Should not raise; should record an execute_script invocation
    svc._safe_send_keys(drv, fake_el, "IMM-2-25")

    assert len(drv.executed) >= 1
    script, args = drv.executed[0]
    # The script should attempt to set the element value and dispatch input
    assert "arguments[0].value" in script
    # The text argument should be passed through
    assert args[-1] == "IMM-2-25"
