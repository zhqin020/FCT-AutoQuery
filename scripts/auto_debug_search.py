#!/usr/bin/env python3
import time
from datetime import datetime, timezone
from pathlib import Path

from selenium.webdriver.common.by import By

from src.services.case_scraper_service import CaseScraperService

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

s = CaseScraperService(headless=False)
try:
    s.initialize_page()
    driver = s._get_driver()

    # Find input as before
    possible_ids = [
        "selectCourtNumber",
        "courtNumber",
        "selectRetcaseCourtNumber",
        "searchd",
    ]
    case_input = None
    for cid in possible_ids:
        try:
            case_input = driver.find_element(By.ID, cid)
            input_id = cid
            break
        except Exception:
            continue
    if case_input is None:
        case_input = driver.find_element(By.XPATH, "//input[@type='text']")
        input_id = "input[type=text]"

    case_number = "IMM-12345-25"
    print(f"Setting #{input_id} = {case_number} (JS set)")
    driver.execute_script("arguments[0].value = arguments[1];", case_input, case_number)

    time.sleep(2)

    # Submit
    submit = None
    try:
        submit = case_input.find_element(
            By.XPATH, "ancestor::form//button[@type='submit']"
        )
    except Exception:
        try:
            submit = case_input.find_element(
                By.XPATH, "ancestor::form//input[@type='submit']"
            )
        except Exception:
            submit = None
    if submit is None:
        try:
            submit = driver.find_element(
                By.XPATH,
                "//button[@type='submit' or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'search') or contains(@class, 'search')]",
            )
        except Exception:
            submit = None

    if submit is None:
        driver.execute_script(
            "var f = arguments[0].closest('form'); if(f){f.submit();} else {document.forms[0] && document.forms[0].submit();}",
            case_input,
        )
    else:
        try:
            submit.click()
        except Exception:
            driver.execute_script("arguments[0].click();", submit)

    # Wait for results to load
    time.sleep(5)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    png = LOG_DIR / f"auto_debug_search_{ts}.png"
    html = LOG_DIR / f"auto_debug_search_{ts}.html"
    try:
        driver.save_screenshot(str(png))
        with open(html, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("Saved screenshot to", png)
        print("Saved page source to", html)
    except Exception as e:
        print("Failed saving artifacts:", e)

    # Check for table and no-data message
    tables = driver.find_elements(By.XPATH, "//table")
    nodata = driver.find_elements(
        By.XPATH,
        "//td[contains(text(), 'No data available') or contains(., 'No data available')]",
    )
    more_links = driver.find_elements(
        By.XPATH,
        "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')]|//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')]",
    )

    print("Tables found:", len(tables))
    print("No-data messages found:", len(nodata))
    print("More links/buttons found:", len(more_links))

finally:
    s.close()
