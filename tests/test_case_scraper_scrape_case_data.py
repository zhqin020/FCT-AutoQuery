import xml.etree.ElementTree as ET

from src.services.case_scraper_service import CaseScraperService
from tests.utils.fake_webelement import FakeWebElement


def _load_fragment(path: str) -> str:
    return open(path, "r", encoding="utf-8").read()


class ClickableElement:
    def __init__(self, fake_el, driver):
        self._el = fake_el
        self._driver = driver

    @property
    def text(self):
        return self._el.text

    def get_attribute(self, name):
        return self._el.get_attribute(name)

    def find_element(self, by, selector):
        found = self._el.find_element(by, selector)
        return ClickableElement(found, self._driver)

    def find_elements(self, by, selector):
        els = self._el.find_elements(by, selector)
        return [ClickableElement(e, self._driver) for e in els]

    def click(self):
        # Simulate that clicking this element causes the modal to become present
        self._driver._modal_shown = True


class FakeDriver:
    def __init__(self, row_root, modal_root):
        self._rows_root = row_root
        self._modal = modal_root
        self._modal_shown = False
        self.page_source = "<html></html>"
        self.current_url = "https://example.test"

    def find_elements(self, by, selector):
        # Return table rows when requested
        if isinstance(selector, str) and selector.endswith("//tr"):
            # find all tr under our row root
            try:
                trs = self._rows_root.find_elements(None, ".//tr")
                return [ClickableElement(t, self) for t in trs]
            except Exception:
                return []

        # Searching for case cell occurrences: return non-empty if case text present
        if isinstance(selector, str) and "contains(normalize-space(.)," in selector:
            # If any td contains the case number text, return a non-empty list
            for td in self._rows_root.find_elements(None, ".//td"):
                if "IMM-123-25" in (td.text or ""):
                    return [ClickableElement(td, self)]
            return []

        return []

    def find_element(self, by, selector):
        # If modal requested and modal has been shown, return it
        if by == "class name" or (by == "class" and selector == "modal-content"):
            if self._modal_shown:
                return self._modal
            raise Exception("Modal not present")

        # Fallback to searching row root for simple id selectors like '#something'
        try:
            return self._rows_root.find_element(by, selector)
        except Exception:
            raise

    def execute_script(self, script, *args, **kwargs):
        # Support JS click fallback by marking modal shown
        if "arguments[0].click" in script:
            self._modal_shown = True
            return True
        # Support form submit JS in other helpers
        return None

    def save_screenshot(self, path):
        return False

    def quit(self):
        return None

    def refresh(self):
        # no-op for tests
        return None


def test_scrape_case_data_happy_path(monkeypatch):
    # Load fixtures and compose a modal that contains header + docket table
    hdr = _load_fragment("tests/fixtures/case_modal/header_table.html")
    dkt = _load_fragment("tests/fixtures/case_modal/docket_table.html")

    # Build a modal fragment that includes both pieces and has class 'modal-content'
    combined = "<div class='modal-content'>" + hdr + dkt + "</div>"
    modal_root = FakeWebElement(ET.fromstring(combined), ET.fromstring(combined))

    # Build a simple results table with a 'More' anchor and the case number
    rows_html = "<root><table><tbody><tr><td>IMM-123-25</td><td>John Doe v. Minister</td><td><a id='more'>More</a></td></tr></tbody></table></root>"
    rows_root = FakeWebElement(ET.fromstring(rows_html), ET.fromstring(rows_html))

    # Create fake driver and monkeypatch WebDriverWait used in module to run instantly
    driver = FakeDriver(rows_root, modal_root)

    # Wrap original WebDriverWait so we can restore later if needed
    import src.services.case_scraper_service as css_mod


    class DummyWait:
        def __init__(self, drv, timeout):
            self._drv = drv

        def until(self, method):
            # Immediately invoke the expected condition callable
            return method(self._drv)

    monkeypatch.setattr(css_mod, "WebDriverWait", DummyWait)

    svc = CaseScraperService(headless=True)

    # Monkeypatch the service _get_driver to return our fake driver
    monkeypatch.setattr(svc, "_get_driver", lambda: driver)

    # Replace the row element's find_element to return a ClickableElement for the 'more' anchor
    # Our FakeWebElement supports the xpath, so wrap returned element
    def row_find_element(by, selector):
        el = rows_root.find_element(by, selector)
        return ClickableElement(el, driver)

    # Monkeypatch rows_root.find_element so that when CaseScraperService calls
    # target_row.find_element it gets a ClickableElement whose click shows the modal
    rows_tr = rows_root.find_element(None, ".//tr")
    # Attach our custom method to the tr element wrapper
    rows_tr.find_element = row_find_element

    # Monkeypatch FakeDriver.find_elements to return our single wrapped tr when asked
    def fake_find_elements(by, selector):
        if isinstance(selector, str) and selector.endswith("//tr"):
            return [ClickableElement(rows_tr, driver)]
        # case detection
        if isinstance(selector, str) and "contains(normalize-space(.), 'IMM-123-25')" in selector:
            return [ClickableElement(rows_tr, driver)]
        return []

    monkeypatch.setattr(driver, "find_elements", fake_find_elements)

    # Also patch driver.find_element for modal detection
    def fake_find_element(by, selector):
        if by == css_mod.By.CLASS_NAME and selector == "modal-content":
            if driver._modal_shown:
                return modal_root
            raise Exception("Modal not present")
        # otherwise fall back
        return rows_root.find_element(by, selector)

    monkeypatch.setattr(driver, "find_element", fake_find_element)

    # Now run scrape_case_data: it should click More, detect modal, parse header and docket entries
    case = svc.scrape_case_data("IMM-123-25")
    assert case is not None
    # Docket entries should be extracted from fixture (3 rows)
    assert hasattr(case, "docket_entries")
    assert len(case.docket_entries) == 3
