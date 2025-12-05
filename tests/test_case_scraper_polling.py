from src.services.case_scraper_service import CaseScraperService
from selenium.webdriver.common.by import By


class FakeElement:
    def __init__(self, text=""):
        self.text = text
        self.id = "fake"

    def clear(self):
        return

    def send_keys(self, text):
        return

    def click(self):
        return

    def get_attribute(self, attr):
        if attr == "value":
            return ""
        return None


class FakeDriver:
    def __init__(self):
        # poll_count is incremented on each polling invocation
        self.poll_count = 0

    def find_element(self, by, value):
        # Return a fake input or submit spinner depending on value
        return FakeElement()

    def find_elements(self, by, value):
        # Only care about the XPaths used during polling
        value_lower = value.lower() if isinstance(value, str) else ''
        if by == By.XPATH and "no data available" in value_lower:
            # First poll: return a 'No data' indicator, second poll: none
            if self.poll_count == 0:
                return [FakeElement(text="No data available")]
            else:
                return []
        if by == By.XPATH and "contains(normalize-space(.), 'IMM-9-21')" in value:
            # First poll: no match, second poll: matching td
            if self.poll_count == 0:
                return []
            else:
                return [FakeElement(text="IMM-9-21")]
        if by == By.XPATH and "//table//tbody//tr" in value:
            if self.poll_count == 0:
                return []
            else:
                return [FakeElement(text="row")]
        return []

    def execute_script(self, *args, **kwargs):
        return

    def save_screenshot(self, path):
        return


def test_polling_allows_transient_no_data(monkeypatch):
    service = CaseScraperService(headless=True)
    fake_driver = FakeDriver()

    # Force service to use the fake driver and skip initializing page details
    monkeypatch.setattr(service, "_get_driver", lambda: fake_driver)
    monkeypatch.setattr(service, "initialize_page", lambda: None)

    # Monkeypatch WebDriverWait.until to simply return a FakeElement for presence checks
    class DummyWait:
        def __init__(self, driver, timeout):
            self.driver = driver
            self.timeout = timeout

        def until(self, cond):
            # Return a FakeElement for any condition requiring presence
            return FakeElement()

    monkeypatch.setattr('src.services.case_scraper_service.WebDriverWait', DummyWait)

    # Intercept the polling calls to increment driver.poll_count per loop
    orig_find_elements = fake_driver.find_elements

    def counting_find_elements(by, value):
        # For polling XPath values, we map poll_count usage
        res = orig_find_elements(by, value)
        value_lower = value.lower() if isinstance(value, str) else ''
        # If this call relates to polling XPaths, increment poll_count when called for 'No data' XPATH
        if by == By.XPATH and "no data available" in value_lower:
            # increment poll count on each call of the no-data check to simulate progression
            fake_driver.poll_count += 1
        return res

    monkeypatch.setattr(fake_driver, 'find_elements', counting_find_elements)

    # Now call search_case with case number IMM-9-21 which should be detected on second poll
    found = service.search_case('IMM-9-21')
    assert found is True


def test_stale_no_data_ignored_until_input_applies(monkeypatch):
    service = CaseScraperService(headless=True)
    fake_driver = FakeDriver()

    # Setup a scenario where the driver shows 'No data' initially and input value is stale
    fake_driver.poll_count = 0

    # Override find_elements: first several polls show 'No data' but input value is a prior case
    orig_find_elements = fake_driver.find_elements
    def custom_find_elements(by, value):
        return orig_find_elements(by, value)
    monkeypatch.setattr(fake_driver, 'find_elements', custom_find_elements)

    # Modify find_element to simulate the case_input having initial stale value
    class FakeInput(FakeElement):
        def __init__(self):
            super().__init__()
            self._value_cycle = ['IMM-5-21', 'IMM-9-21']
            self._reads = 0
        def get_attribute(self, attr):
            if attr == 'value':
                # first read returns stale value, then updated
                val = self._value_cycle[min(self._reads, len(self._value_cycle)-1)]
                self._reads += 1
                return val
            return None

    monkeypatch.setattr(fake_driver, 'find_element', lambda by, value: FakeInput())
    monkeypatch.setattr(service, "_get_driver", lambda: fake_driver)
    monkeypatch.setattr(service, "initialize_page", lambda: None)

    class DummyWait2:
        def __init__(self, driver, timeout):
            pass
        def until(self, cond):
            return FakeInput()

    monkeypatch.setattr('src.services.case_scraper_service.WebDriverWait', DummyWait2)

    # counting find_elements to increment poll_count
    def counting_find_elements2(by, value):
        res = orig_find_elements(by, value)
        value_lower = value.lower() if isinstance(value, str) else ''
        if by == By.XPATH and "no data available" in value_lower:
            fake_driver.poll_count += 1
        return res

    monkeypatch.setattr(fake_driver, 'find_elements', counting_find_elements2)

    # Now call search_case: expecting that despite initial 'No data', we continue and return True once input updates
    found = service.search_case('IMM-9-21')
    assert found is True


def test_no_data_threshold_respected(monkeypatch):
    """Ensure search_case uses the configured safe_stop_no_records threshold for 'No data' detection."""
    service = CaseScraperService(headless=True)
    fake_driver = FakeDriver()

    # simulate that the driver always returns 'No data available' for the first N polls
    # where N == Config.get_safe_stop_no_records(), thereby causing search_case to
    # treat it as final no-results.
    from src.lib.config import Config
    threshold = int(Config.get_safe_stop_no_records())

    # Create a driver that returns 'No data available' for threshold polls, then a matching row
    class ThresholdDriver(FakeDriver):
        def __init__(self):
            super().__init__()
            self._counter = 0

        def find_elements(self, by, value):
            value_lower = value.lower() if isinstance(value, str) else ''
            if by == By.XPATH and "no data available" in value_lower:
                if self._counter < threshold:
                    self._counter += 1
                    return [FakeElement(text="No data available")]
                else:
                    return []
            if by == By.XPATH and "contains(normalize-space(.), 'IMM-9-21')" in value:
                # After threshold polls, the row appears (for this test we don't expect to get this far)
                if self._counter > threshold:
                    return [FakeElement(text="IMM-9-21")]
                return []
            if by == By.XPATH and "//table//tbody//tr" in value:
                if self._counter > threshold:
                    return [FakeElement(text="row")]
                return []
            return []
        def find_element(self, by, value):
            # Return a fake input that reports the correct case number so that
            # 'No data available' polling is associated with the requested
            # case number and increments the stable 'no_data' streak.
            class FakeInput(FakeElement):
                def __init__(self, text=''):
                    super().__init__(text)
                    self._value = 'IMM-9-21'
                def get_attribute(self, attr):
                    if attr == 'value':
                        return self._value
                    return None
            return FakeInput()

    d = ThresholdDriver()
    monkeypatch.setattr(service, "_get_driver", lambda: d)
    monkeypatch.setattr(service, "initialize_page", lambda: None)

    class DummyWait3:
        def __init__(self, driver, timeout):
            pass
        def until(self, cond):
            return FakeElement()

    monkeypatch.setattr('src.services.case_scraper_service.WebDriverWait', DummyWait3)

    found = service.search_case('IMM-9-21')
    assert found is False


def test_polling_numeric_variant_detected_early(monkeypatch):
    """If the table rows appear with a leading-zero variant, detection should succeed in polling loop."""
    service = CaseScraperService(headless=True)
    fake_driver = FakeDriver()

    # This driver returns 'No data' initially, then returns a table row with IMM-0001-25
    class VariantDriver(FakeDriver):
        def __init__(self):
            super().__init__()
            self._counter = 0
        def find_elements(self, by, value):
            value_lower = value.lower() if isinstance(value, str) else ''
            if by == By.XPATH and "no data available" in value_lower:
                if self._counter < 3:
                    self._counter += 1
                    return [FakeElement(text="No data available")]
                return []
            if by == By.XPATH and "contains(normalize-space(.), 'IMM-1-25')" in value:
                return []
            if by == By.XPATH and "//table//tbody//tr" in value:
                if self._counter >= 3:
                    return [FakeElement(text="IMM-0001-25")]
                return []
            return []

    d = VariantDriver()
    monkeypatch.setattr(service, "_get_driver", lambda: d)
    monkeypatch.setattr(service, "initialize_page", lambda: None)
    class DummyWait4:
        def __init__(self, driver, timeout):
            pass
        def until(self, cond):
            return FakeElement()
    monkeypatch.setattr('src.services.case_scraper_service.WebDriverWait', DummyWait4)

    found = service.search_case('IMM-1-25')
    assert found is True


def test_polling_numeric_variant_handles_various_formatting(monkeypatch):
    """Ensure search_case detects numeric variants for case numbers formatted with zero-padding and alternate separators."""
    service = CaseScraperService(headless=True)
    fake_driver = FakeDriver()

    variants = [
        'IMM-0005-21',
        'IMM - 5 - 21',
        'IMM/5/21',
        'IMM–5–21',
        'IMM—005—21',
        'IMM 005 21',
        'IMM-05-21',
    ]

    for variant_text in variants:
        class VariantDriver2(FakeDriver):
            def __init__(self, text):
                super().__init__()
                self._counter = 0
                self._vtext = text

            def find_elements(self, by, value):
                value_lower = value.lower() if isinstance(value, str) else ''
                if by == By.XPATH and "no data available" in value_lower:
                    if self._counter < 2:
                        self._counter += 1
                        return [FakeElement(text="No data available")]
                    return []
                if by == By.XPATH and "contains(normalize-space(.), 'IMM-5-21')" in value:
                    return []
                if by == By.XPATH and "//table//tbody//tr" in value:
                    if self._counter >= 2:
                        return [FakeElement(text=self._vtext)]
                    return []
                return []

        d = VariantDriver2(variant_text)
        monkeypatch.setattr(service, "_get_driver", lambda: d)
        monkeypatch.setattr(service, "initialize_page", lambda: None)

        class DummyWaitV:
            def __init__(self, driver, timeout):
                pass

            def until(self, cond):
                return FakeElement()

        monkeypatch.setattr('src.services.case_scraper_service.WebDriverWait', DummyWaitV)
        assert service.search_case('IMM-5-21') is True


def test_polling_placeholder_stops_early(monkeypatch):
    """If the table rows contain the DataTables placeholder 'No data available in table', polling should stop early and return no-results."""
    service = CaseScraperService(headless=True)
    fake_driver = FakeDriver()

    class PlaceholderDriver(FakeDriver):
        def __init__(self):
            super().__init__()
            self._counter = 0

        def find_elements(self, by, value):
            value_lower = value.lower() if isinstance(value, str) else ''
            if by == By.XPATH and "no data available" in value_lower:
                # Return it immediately
                return [FakeElement(text="No data available")]
            if by == By.XPATH and "contains(normalize-space(.), 'IMM-5-21')" in value:
                return []
            if by == By.XPATH and "//table//tbody//tr" in value:
                # Return a placeholder row in the results table
                return [FakeElement(text="No data available in table")]
            return []

    d = PlaceholderDriver()
    monkeypatch.setattr(service, "_get_driver", lambda: d)
    monkeypatch.setattr(service, "initialize_page", lambda: None)
    # Simulate the case input reporting the correct case value so 'No data available' is not stale
    class FakeInput(FakeElement):
        def __init__(self):
            super().__init__()
        def get_attribute(self, attr):
            if attr == 'value':
                return 'IMM-5-21'
            return None
    monk_find_element = lambda by, value: FakeInput()
    monkeypatch.setattr(d, 'find_element', monk_find_element)

    class DummyWaitP:
        def __init__(self, driver, timeout):
            pass

        def until(self, cond):
            return FakeInput()

    monkeypatch.setattr('src.services.case_scraper_service.WebDriverWait', DummyWaitP)

    found = service.search_case('IMM-5-21')
    assert found is False
    # ensure the driver did not poll up to the default safe_stop threshold
    from src.lib.config import Config
    safe_stop = int(Config.get_safe_stop_no_records())
    assert d.poll_count < safe_stop


def test_polling_placeholder_stops_early_french(monkeypatch):
    """Ensure French placeholders also cause early stop."""
    service = CaseScraperService(headless=True)
    fake_driver = FakeDriver()

    class FrPlaceholderDriver(FakeDriver):
        def __init__(self):
            super().__init__()
        def find_elements(self, by, value):
            print('Fr find_elements called value:', value)
            value_lower = value.lower() if isinstance(value, str) else ''
            if by == By.XPATH and "aucun résultat" in value_lower:
                # This is the placeholder match built using the phrase XPATH
                return [FakeElement(text="Aucun résultat disponible")]
            if by == By.XPATH and "contains(normalize-space(.), 'IMM-5-21')" in value:
                return []
            if by == By.XPATH and "//table//tbody//tr" in value:
                return [FakeElement(text="Aucun résultat disponible")]
            return []

    d2 = FrPlaceholderDriver()
    monkeypatch.setattr(service, "_get_driver", lambda: d2)
    monkeypatch.setattr(service, "initialize_page", lambda: None)
    class DummyWaitPf:
        def __init__(self, driver, timeout):
            pass
        def until(self, cond):
            return FakeElement()
    monkeypatch.setattr('src.services.case_scraper_service.WebDriverWait', DummyWaitPf)

    # ensure the input reports the correct case value so our placeholder is valid
    class FakeInput(FakeElement):
        def __init__(self):
            super().__init__()
        def get_attribute(self, attr):
            if attr == 'value':
                return 'IMM-5-21'
            return None
    monkeypatch.setattr(d2, 'find_element', lambda by, value: FakeInput())
    found = service.search_case('IMM-5-21')
    assert found is False


def test_polling_placeholder_stops_early_spanish(monkeypatch):
    """Ensure Spanish placeholders also cause early stop."""
    service = CaseScraperService(headless=True)
    fake_driver = FakeDriver()

    class EsPlaceholderDriver(FakeDriver):
        def __init__(self):
            super().__init__()
        def find_elements(self, by, value):
            print('Es find_elements called value:', value)
            value_lower = value.lower() if isinstance(value, str) else ''
            if by == By.XPATH and "sin datos" in value_lower:
                return [FakeElement(text="Sin datos disponibles")]
            if by == By.XPATH and "contains(normalize-space(.), 'IMM-5-21')" in value:
                return []
            if by == By.XPATH and "//table//tbody//tr" in value:
                return [FakeElement(text="Sin datos disponibles")]
            return []

    d3 = EsPlaceholderDriver()
    monkeypatch.setattr(service, "_get_driver", lambda: d3)
    monkeypatch.setattr(service, "initialize_page", lambda: None)
    class DummyWaitEs:
        def __init__(self, driver, timeout):
            pass
        def until(self, cond):
            return FakeElement()
    monkeypatch.setattr('src.services.case_scraper_service.WebDriverWait', DummyWaitEs)

    class FakeInput2(FakeElement):
        def __init__(self):
            super().__init__()
        def get_attribute(self, attr):
            if attr == 'value':
                return 'IMM-5-21'
            return None
    monkeypatch.setattr(d3, 'find_element', lambda by, value: FakeInput2())
    found = service.search_case('IMM-5-21')
    assert found is False


def test_polling_placeholder_stops_early_portuguese(monkeypatch):
    """Ensure Portuguese placeholders also cause early stop."""
    service = CaseScraperService(headless=True)
    fake_driver = FakeDriver()

    class PtPlaceholderDriver(FakeDriver):
        def __init__(self):
            super().__init__()
        def find_elements(self, by, value):
            print('Pt find_elements called value:', value)
            value_lower = value.lower() if isinstance(value, str) else ''
            if by == By.XPATH and "sem dados" in value_lower:
                return [FakeElement(text="Sem dados disponíveis")]
            if by == By.XPATH and "contains(normalize-space(.), 'IMM-5-21')" in value:
                return []
            if by == By.XPATH and "//table//tbody//tr" in value:
                return [FakeElement(text="Sem dados disponíveis")]
            return []

    d4 = PtPlaceholderDriver()
    monkeypatch.setattr(service, "_get_driver", lambda: d4)
    monkeypatch.setattr(service, "initialize_page", lambda: None)

    class DummyWaitPt:
        def __init__(self, driver, timeout):
            pass
        def until(self, cond):
            return FakeElement()

    monkeypatch.setattr('src.services.case_scraper_service.WebDriverWait', DummyWaitPt)
    class FakeInput3(FakeElement):
        def __init__(self):
            super().__init__()
        def get_attribute(self, attr):
            if attr == 'value':
                return 'IMM-5-21'
            return None
    monkeypatch.setattr(d4, 'find_element', lambda by, value: FakeInput3())
    found = service.search_case('IMM-5-21')
    assert found is False
