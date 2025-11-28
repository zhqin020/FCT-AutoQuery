import xml.etree.ElementTree as ET

from src.services import case_scraper_service as css
from src.services.case_scraper_service import CaseScraperService


class SubmitElement:
    def __init__(self):
        self.clicked = False

    def click(self):
        self.clicked = True


class InputElement:
    def __init__(self, submit=None, raise_on_find=False):
        self._submit = submit
        self._raise = raise_on_find

    def find_element(self, by, selector):
        if self._raise:
            raise Exception("not found")
        if self._submit is None:
            raise Exception("not found")
        return self._submit


class FakeDriver:
    def __init__(self):
        self.executed = []

    def execute_script(self, script, *args):
        self.executed.append((script, args))


def test_submit_search_using_input_ancestor_button():
    submit = SubmitElement()
    inp = InputElement(submit=submit, raise_on_find=False)
    drv = FakeDriver()
    svc = CaseScraperService(headless=True)

    # Should use input_element.find_element and click the submit element
    svc._submit_search(drv, inp)
    assert submit.clicked is True


def test_submit_search_uses_wait_clickable(monkeypatch):
    # input element cannot find ancestor submits
    inp = InputElement(submit=None, raise_on_find=True)
    drv = FakeDriver()
    submit = SubmitElement()
    svc = CaseScraperService(headless=True)

    # Monkeypatch WebDriverWait in module to return an object whose until() returns our submit
    class DummyWait:
        def __init__(self, driver, timeout):
            pass

        def until(self, cond):
            return submit

    monkeypatch.setattr(css, "WebDriverWait", DummyWait)

    svc._submit_search(drv, inp)
    assert submit.clicked is True


def test_submit_search_js_form_submit_fallback(monkeypatch):
    inp = InputElement(submit=None, raise_on_find=True)
    drv = FakeDriver()
    svc = CaseScraperService(headless=True)

    # Make WebDriverWait.until raise so submit remains None
    class DummyWaitRaise:
        def __init__(self, driver, timeout):
            pass

        def until(self, cond):
            raise Exception("no clickable")

    monkeypatch.setattr(css, "WebDriverWait", DummyWaitRaise)

    # Should not raise; should call driver.execute_script with the form-submit script
    svc._submit_search(drv, inp)
    assert len(drv.executed) >= 1
    script, args = drv.executed[0]
    assert "closest('form')" in script or "submit()" in script
