import xml.etree.ElementTree as ET

from src.services.case_scraper_service import CaseScraperService
from tests.utils.fake_webelement import FakeWebElement


class FakeDriver:
    def __init__(self, rows_root, modal_root):
        self._rows_root = rows_root
        self._modal = modal_root
        self._modal_shown = False
        self.page_source = "<html></html>"
        self.current_url = "https://example.test"

    def find_elements(self, by, selector):
        if isinstance(selector, str) and selector.endswith("//tr"):
            return self._rows_root.find_elements(None, ".//tr")
        return []

    def find_element(self, by, selector=None):
        if isinstance(by, tuple):
            by, selector = by
        if by == "class name" and selector == "modal-content":
            if self._modal_shown:
                return self._modal
            raise Exception("Modal not present")
        return self._rows_root.find_element(by, selector)

    def execute_script(self, script, *args, **kwargs):
        if "arguments[0].click" in script:
            self._modal_shown = True
            return True
        return None

    def save_screenshot(self, p):
        return False

    def refresh(self):
        return None

    def quit(self):
        return None


class Clickable:
    def __init__(self, fake_el, driver):
        self._el = fake_el
        self._driver = driver

    @property
    def text(self):
        return self._el.text

    def get_attribute(self, name):
        return self._el.get_attribute(name)

    def find_element(self, by, selector):
        return self._el.find_element(by, selector)

    def click(self):
        # clicking the control opens modal
        self._driver._modal_shown = True


def test_last_cell_fallback_opens_modal(monkeypatch):
    # Row with last cell containing a button
    rows_html = "<root><table><tbody><tr><td>IMM-LAST-25</td><td>Style</td><td><button id='last'>Open</button></td></tr></tbody></table></root>"
    rows_root = FakeWebElement(ET.fromstring(rows_html), ET.fromstring(rows_html))

    modal_html = "<div class='modal-content'><p><strong>Court File :</strong> IMM-LAST-25</p><table><tbody></tbody></table></div>"
    modal_root = FakeWebElement(ET.fromstring(modal_html), ET.fromstring(modal_html))

    driver = FakeDriver(rows_root, modal_root)

    svc = CaseScraperService(headless=True)
    monkeypatch.setattr(svc, "_get_driver", lambda: driver)

    # Use WebDriverWait fallback: return a clickable element that opens the modal
    tr = rows_root.find_element(None, ".//tr")
    monkeypatch.setattr(driver, "find_elements", lambda by, sel: [tr] if sel.endswith("//tr") else [])

    import src.services.case_scraper_service as css_mod

    fake_anchor_el = FakeWebElement(ET.fromstring("<a>More</a>"), ET.fromstring("<a>More</a>"))

    class DummyWait:
        def __init__(self, drv, timeout):
            self._drv = drv

        def until(self, method):
            # Return a Clickable that will open the modal when clicked
            return Clickable(fake_anchor_el, driver)

    monkeypatch.setattr(css_mod, "WebDriverWait", DummyWait)

    # Stub header/docket extraction so scrape completes once modal is shown
    monkeypatch.setattr(CaseScraperService, "_extract_case_header", lambda self, m: {"case_id": "IMM-LAST-25"})
    monkeypatch.setattr(CaseScraperService, "_extract_docket_entries", lambda self, m, cid: [])
    monkeypatch.setattr(CaseScraperService, "_close_modal", lambda self: None)

    case = svc.scrape_case_data("IMM-LAST-25")
    assert case is not None
    assert case.case_id == "IMM-LAST-25"


def test_row_click_fallback_opens_modal(monkeypatch):
    # Row present but no in-row control; clicking the row (via JS) should open modal
    rows_html = "<root><table><tbody><tr><td>IMM-ROW-25</td><td>Style</td><td></td></tr></tbody></table></root>"
    rows_root = FakeWebElement(ET.fromstring(rows_html), ET.fromstring(rows_html))

    modal_html = "<div class='modal-content'><p><strong>Court File :</strong> IMM-ROW-25</p><table><tbody></tbody></table></div>"
    modal_root = FakeWebElement(ET.fromstring(modal_html), ET.fromstring(modal_html))

    driver = FakeDriver(rows_root, modal_root)

    svc = CaseScraperService(headless=True)
    monkeypatch.setattr(svc, "_get_driver", lambda: driver)

    tr = rows_root.find_element(None, ".//tr")

    # Ensure no in-row more control
    def tr_find_element(by, selector):
        # Return not found for in-row controls so the row-click fallback is used.
        raise Exception("not found")

    tr.find_element = tr_find_element

    # For row-click fallback use the same WebDriverWait fallback to return a clickable
    monkeypatch.setattr(driver, "find_elements", lambda by, sel: [tr] if sel.endswith("//tr") else [])

    fake_anchor_el2 = FakeWebElement(ET.fromstring("<a>More</a>"), ET.fromstring("<a>More</a>"))

    import src.services.case_scraper_service as css_mod

    class DummyWait2:
        def __init__(self, drv, timeout):
            self._drv = drv

        def until(self, method):
            return Clickable(fake_anchor_el2, driver)

    monkeypatch.setattr(css_mod, "WebDriverWait", DummyWait2)

    monkeypatch.setattr(CaseScraperService, "_extract_case_header", lambda self, m: {"case_id": "IMM-ROW-25"})
    monkeypatch.setattr(CaseScraperService, "_extract_docket_entries", lambda self, m, cid: [])
    monkeypatch.setattr(CaseScraperService, "_close_modal", lambda self: None)

    case = svc.scrape_case_data("IMM-ROW-25")
    assert case is not None
    assert case.case_id == "IMM-ROW-25"
