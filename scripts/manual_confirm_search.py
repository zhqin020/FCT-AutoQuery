#!/usr/bin/env python3
import time

from selenium.webdriver.common.by import By

from src.services.case_scraper_service import CaseScraperService

s = CaseScraperService(headless=False)
try:
    s.initialize_page()
    print("Initialized page. Locating input...")
    driver = s._get_driver()

    possible_ids = [
        "selectCourtNumber",
        "courtNumber",
        "selectRetcaseCourtNumber",
        "searchd",
    ]
    case_input = None
    input_id = None
    for cid in possible_ids:
        try:
            case_input = driver.find_element(By.ID, cid)
            input_id = cid
            break
        except Exception:
            continue

    if case_input is None:
        # fallback to any text input
        case_input = driver.find_element(By.XPATH, "//input[@type='text']")
        input_id = "input[type=text]"

    case_number = "IMM-12345-25"
    print(f"Entering case number into #{input_id}: {case_number}")

    # Ensure court select is set to Federal Court ('t') if present so the
    # dedicated search tab returns Federal Court results.
    possible_select_ids = [
        "tab02selectCourt",
        "tab01selectCourt",
        "tab03selectCourt",
        "court",
    ]
    for sid in possible_select_ids:
        try:
            sel = driver.find_element(By.ID, sid)
            driver.execute_script(
                "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change'));",
                sel,
                "t",
            )
            print(f"Set court select #{sid} to Federal Court (t)")
            break
        except Exception:
            continue

    # Set the input value and dispatch input/change events so site JS behaves
    # as if the user typed the value (but don't use document.forms[].submit()).
    try:
        driver.execute_script(
            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input')); arguments[0].dispatchEvent(new Event('change'));",
            case_input,
            case_number,
        )
        print("Value set and input/change events dispatched")
    except Exception:
        print("JS set+dispatch failed; falling back to _safe_send_keys")
        s._safe_send_keys(driver, case_input, case_number)

    # Wait 2 seconds so you can see the typed value before submission
    print("Pausing 2 seconds before submitting...")
    time.sleep(2)

    # Try to find a submit control related to the input and click it
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

    # Prefer clicking the tab-specific submit button (tab02Submit) which runs
    # the page's JS handlers. Avoid using form.submit() which bypasses handlers.
    submitted = False
    try:
        ts = driver.find_element(By.ID, "tab02Submit")
        print("Clicking #tab02Submit")
        try:
            ts.click()
        except Exception:
            driver.execute_script("arguments[0].click();", ts)
        submitted = True
    except Exception:
        pass

    if not submitted and submit is not None:
        print("Clicking fallback submit button")
        try:
            submit.click()
        except Exception:
            driver.execute_script("arguments[0].click();", submit)
        submitted = True

    if not submitted:
        print(
            "No suitable submit button found — attempting to trigger Enter key on input"
        )
        try:
            driver.execute_script(
                "arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key:'Enter'}));",
                case_input,
            )
        except Exception:
            print("Could not dispatch Enter key")

    print("Search submitted — waiting up to 10 seconds for results...")

    # Wait for either results table or an informative text ('Showing 1')
    found = False
    for _ in range(10):
        time.sleep(1)
        if driver.find_elements(By.XPATH, "//table//tbody//tr"):
            found = True
            break
        if driver.find_elements(
            By.XPATH, "//*[contains(text(), 'Showing') and contains(text(), 'entries')]"
        ):
            found = True
            break

    if not found:
        # Save diagnostics for inspection
        try:
            from datetime import datetime

            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            driver.save_screenshot(f"logs/manual_confirm_search_fail_{ts}.png")
            with open(
                f"logs/manual_confirm_search_fail_{ts}.html", "w", encoding="utf-8"
            ) as f:
                f.write(driver.page_source)
            print("No results detected; saved diagnostics in logs/")
        except Exception as e:
            print("Failed saving diagnostics:", e)

    print("Done — please inspect the browser. Press Enter to close.")
    input()

finally:
    s.close()
