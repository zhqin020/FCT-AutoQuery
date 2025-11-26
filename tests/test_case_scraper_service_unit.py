def test_case_scraper_service_basic_methods_exist():
    from src.services.case_scraper_service import CaseScraperService

    svc = CaseScraperService(headless=True)
    assert callable(getattr(svc, "initialize_page", None))
    assert callable(getattr(svc, "_get_driver", None))
    assert callable(getattr(svc, "_restart_driver", None))
