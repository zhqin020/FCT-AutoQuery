import xml.etree.ElementTree as ET

from selenium.common.exceptions import StaleElementReferenceException

from src.services.case_scraper_service import CaseScraperService
from tests.utils.fake_webelement import FakeWebElement


class ReplacementClickable:
    def __init__(self, fake_el, driver, modal_root):
        self._el = fake_el
        self._driver = driver
        self._modal = modal_root

    @property
    def text(self):
        return self._el.text

    def get_attribute(self, name):
        return self._el.get_attribute(name)

    def find_element(self, by, selector):
        return self._el.find_element(by, selector)

    def find_elements(self, by, selector):
        return self._el.find_elements(by, selector)

    def click(self):
        # On successful click, reveal the modal
        self._driver._modal_shown = True


class StaleClickable(ReplacementClickable):
    def __init__(self, fake_el, driver, modal_root):
        super().__init__(fake_el, driver, modal_root)
        self._raised = False

    def click(self):
        # Raise StaleElementReferenceException the first time, then behave
        if not self._raised:
            self._raised = True
            raise StaleElementReferenceException("stale simulated")
        return super().click()


class FakeDriver:
    def __init__(self, rows_root, modal_root):
        self._rows_root = rows_root
        self._modal = modal_root
        self._modal_shown = False
        self.page_source = "<html></html>"
        self.current_url = "https://example.test"

    def find_elements(self, by, selector):
        # return rows when requested
        if isinstance(selector, str) and selector.endswith("//tr"):
            trs = self._rows_root.find_elements(None, ".//tr")
            return trs
        # case detection
        if isinstance(selector, str) and "contains(normalize-space(.)," in selector:
            tds = self._rows_root.find_elements(None, ".//td")
            return [td for td in tds if "IMM-STAR-25" in (td.text or "")]
        return []

    def find_element(self, by, selector):
        # modal presence check
        if isinstance(by, tuple):
            by, selector = by
        if by == "class name" and selector == "modal-content":
            if self._modal_shown:
                return self._modal
            raise Exception("Modal not present")
        # else delegate to rows root
        return self._rows_root.find_element(by, selector)

    def execute_script(self, script, *args, **kwargs):
        # simulate JS click making modal appear
        if "arguments[0].click" in script:
            self._modal_shown = True
            return True
        return None

    def save_screenshot(self, path):
        return False

    def refresh(self):
        return None

    def quit(self):
        return None


def test_scrape_case_data_stale_retry(monkeypatch):
    # Simpler approach: simulate no per-row 'More' control so code uses global
    # WebDriverWait for the 'More' link. WebDriverWait will return a stale
    # clickable first, then a replacement clickable on retry.
    rows_html = "<root><table><tbody></tbody></table></root>"
    rows_root = FakeWebElement(ET.fromstring(rows_html), ET.fromstring(rows_html))

    modal_html = "<div class='modal-content'><p><strong>Court File :</strong> IMM-STAR-25</p><table><tbody></tbody></table></div>"
    modal_root = FakeWebElement(ET.fromstring(modal_html), ET.fromstring(modal_html))

    driver = FakeDriver(rows_root, modal_root)

    import src.services.case_scraper_service as css_mod

    # Prepare a fake anchor element to wrap
    fake_anchor_el = FakeWebElement(ET.fromstring("<a>More</a>"), ET.fromstring("<a>More</a>"))

    # Responses for WebDriverWait.until: first a stale clickable, then a replacement clickable, then presence of modal
    responses = []

    responses.append(StaleClickable(fake_anchor_el, driver, modal_root))
    responses.append(ReplacementClickable(fake_anchor_el, driver, modal_root))
    responses.append(modal_root)

    class SeqWait:
        def __init__(self, drv, timeout):
            self._drv = drv

        def until(self, method):
            if not responses:
                return method(self._drv)
            return responses.pop(0)

    monkeypatch.setattr(css_mod, "WebDriverWait", SeqWait)

    svc = CaseScraperService(headless=True)
    monkeypatch.setattr(svc, "_get_driver", lambda: driver)

    # driver.find_elements: no rows
    monkeypatch.setattr(driver, "find_elements", lambda by, selector: [])

    # driver.find_element: for modal presence check return modal if modal_shown True
    def fake_find_element(by, selector=None):
        if isinstance(by, tuple):
            by, selector = by
        if by == css_mod.By.CLASS_NAME and selector == "modal-content":
            if driver._modal_shown:
                return modal_root
            raise Exception("Modal not present")
        raise Exception("not found")

    monkeypatch.setattr(driver, "find_element", fake_find_element)

    case = svc.scrape_case_data("IMM-STAR-25")
    assert case is not None
    assert case.case_id == "IMM-STAR-25"
