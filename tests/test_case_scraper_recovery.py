import pytest
from unittest.mock import MagicMock

from src.services.case_scraper_service import CaseScraperService


def test_restart_driver_called_on_dead_driver(monkeypatch):
    svc = CaseScraperService(headless=True)

    # Simulate an existing driver that raises on current_window_handle access
    fake_driver = MagicMock()
    type(fake_driver).current_window_handle = property(lambda self: (_ for _ in ()).throw(Exception("session closed")))
    svc._driver = fake_driver
    svc._max_restarts = 1

    # Patch _setup_driver to return a new fake driver
    new_driver = MagicMock()
    monkeypatch.setattr(svc, "_setup_driver", lambda: new_driver)

    drv = svc._get_driver()
    assert drv is new_driver
    assert svc._driver is new_driver


def test_restart_exceeds_limit_raises(monkeypatch):
    svc = CaseScraperService(headless=True)
    # make _setup_driver raise so restart fails; ensure accessing current_window_handle raises
    fake_driver = MagicMock()
    type(fake_driver).current_window_handle = property(lambda self: (_ for _ in ()).throw(Exception("session closed")))
    svc._driver = fake_driver
    def bad_setup():
        raise RuntimeError("cannot start")
    svc._setup_driver = bad_setup
    svc._max_restarts = 0

    with pytest.raises(RuntimeError):
        svc._get_driver()
