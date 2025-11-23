#!/usr/bin/env python3
import argparse
import os
import time
from datetime import datetime, timezone

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from src.services.case_scraper_service import CaseScraperService

# CLI: allow non-interactive runs via `--yes` or `--non-interactive`.
parser = argparse.ArgumentParser(
    description="Run a quick smoke search and open the modal for a court case"
)
parser.add_argument(
    "--yes",
    "-y",
    action="store_true",
    help="Run non-interactively; skip confirmation prompts",
)
parser.add_argument(
    "--non-interactive",
    action="store_true",
    help="Alias for --yes",
)
parser.add_argument(
    "--service-class",
    help=(
        "Optional dotted import path to a Service class to instantiate, e.g. "
        "tests.integration.fake_service.FakeService"
    ),
)
parser.add_argument(
    "--case",
    help="Case number to search (e.g. IMM-12345-22). Overrides built-in default.",
)
args = parser.parse_args()

# Resolve non-interactive preference: CLI flag takes precedence,
# otherwise respect AUTO_CONFIRM environment variable (legacy support).
env_auto = os.environ.get("AUTO_CONFIRM")
env_truthy = bool(env_auto and env_auto not in ("0", "false", "False"))
non_interactive = bool(args.yes or args.non_interactive or env_truthy)

case_number = args.case or os.environ.get("CASE_NUMBER") or "IMM-12345-25"


def import_class(dotted_path: str):
    """Import a class from a dotted path string."""
    # Support two formats:
    #  - dotted.module.ClassName
    #  - file_path.py:ClassName
    import importlib
    import importlib.machinery
    import importlib.util

    if ":" in dotted_path:
        file_path, class_name = dotted_path.rsplit(":", 1)
        loader = importlib.machinery.SourceFileLoader(class_name, file_path)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return getattr(module, class_name)

    module_path, _, class_name = dotted_path.rpartition(".")
    if not module_path:
        raise ImportError(f"Invalid service class path: {dotted_path}")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


# Instantiate service: prefer user-provided class (for tests), otherwise
# use the real CaseScraperService.
if args.service_class:
    try:
        ServiceClass = import_class(args.service_class)
        s = ServiceClass(headless=False)
        print(f"Using injected service class: {args.service_class}")
    except Exception as e:
        raise SystemExit(
            f"Failed to import/instantiate service class '{args.service_class}': {e}"
        )
else:
    s = CaseScraperService(headless=False)

# If the provided service implements a high-level fetch method, use it and
# skip the browser-driven orchestration. This allows injection of a fake
# service for CI tests.
if hasattr(s, "fetch_case_and_docket"):
    try:
        case_data, docket_entries = s.fetch_case_and_docket(
            case_number, non_interactive
        )

        # Export structured JSON to output/ (same format as below)
        import json
        from pathlib import Path

        out_dir = Path("output")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_case = (case_data.get("case_id") or case_number).replace("/", "_")
        out_path = out_dir / f"{safe_case}_{ts}.json"

        cd = dict(case_data)
        if isinstance(cd.get("filing_date"), (str,)):
            pass
        else:
            try:
                if cd.get("filing_date") is not None:
                    cd["filing_date"] = cd["filing_date"].isoformat()
            except Exception:
                pass

        payload = {
            "case": cd,
            "docket_entries": [
                (
                    e.to_dict()
                    if hasattr(e, "to_dict")
                    else {
                        "doc_id": getattr(e, "doc_id", None),
                        "case_id": getattr(e, "case_id", None),
                        "entry_date": (
                            getattr(e, "entry_date", None).isoformat()
                            if getattr(e, "entry_date", None)
                            else None
                        ),
                        "entry_office": getattr(e, "entry_office", None),
                        "summary": getattr(e, "summary", None),
                    }
                )
                for e in docket_entries
            ],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

        with open(out_path, "w", encoding="utf-8") as jf:
            json.dump(payload, jf, ensure_ascii=False, indent=2)
        print(f"Saved structured JSON to {out_path}")
        s.close()
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as e:
        print("Injected service fetch failed:", e)
        # fall back to browser-driven flow
try:
    s.initialize_page()
    driver = s._get_driver()
    # Ensure the search-by-court-number tab is active (robust click)
    try:
        tab = driver.find_element(
            By.XPATH,
            "//a[contains(., 'Search by court number') or contains(., 'Search by Court Number') or contains(@class,'TabButton') and contains(., 'Search by court number')]",
        )
        try:
            tab.click()
        except Exception:
            driver.execute_script("arguments[0].click();", tab)
        time.sleep(0.5)
    except Exception:
        # if not found, assume initialize_page already selected the tab
        pass

    # set court select (ensure it's set and verified)
    possible_select_ids = [
        "tab02selectCourt",
        "tab01selectCourt",
        "tab03selectCourt",
        "court",
    ]
    sel = None
    for sid in possible_select_ids:
        try:
            candidate = driver.find_element(By.ID, sid)
            if candidate.is_displayed():
                sel = candidate
                break
        except Exception:
            continue
    if sel:
        try:
            driver.execute_script(
                "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change'));",
                sel,
                "t",
            )
            # verify value applied
            v = driver.execute_script("return arguments[0].value;", sel)
            print("Court select set to:", v)
        except Exception:
            print("Warning: could not set court select via JS")
    else:
        print("No court select element found; continuing")

    # Find a visible input within the active tab area. Prefer specific ids
    possible_input_ids = [
        "selectCourtNumber",
        "courtNumber",
        "selectRetcaseCourtNumber",
        "searchd",
    ]
    case_input = None
    for pid in possible_input_ids:
        try:
            els = driver.find_elements(By.ID, pid)
            for el in els:
                if el.is_displayed() and el.is_enabled():
                    case_input = el
                    break
            if case_input:
                break
        except Exception:
            continue

    if case_input is None:
        # Fallback: any visible text input inside the search tab container
        try:
            container = driver.find_element(
                By.XPATH,
                "//div[contains(@class,'tab-contents') and (not(contains(@style,'display: none')) or contains(@style,''))]",
            )
            case_input = container.find_element(
                By.XPATH,
                ".//input[@type='text' and not(contains(@style,'display:none'))]",
            )
        except Exception:
            try:
                case_input = driver.find_element(
                    By.XPATH,
                    "//input[@type='text' and @id and not(contains(@style,'display:none'))]",
                )
            except Exception:
                case_input = None

    if case_input is None:
        raise SystemExit("Could not locate a visible case-number input")

    # 3. Focus text input, type the case number, and verify the input value
    try:
        try:
            case_input.click()
        except Exception:
            driver.execute_script("arguments[0].focus();", case_input)

        s._safe_send_keys(driver, case_input, case_number)

        # small stabilization before submit
        time.sleep(0.25)

        # verify input contains case number
        try:
            current = driver.execute_script("return arguments[0].value;", case_input)
        except Exception:
            current = case_input.get_attribute("value") if case_input else ""

        print("Input value after typing:", current)
        if case_number not in (current or ""):
            print(
                "Warning: typed value does not match expected case number; retrying send_keys"
            )
            s._safe_send_keys(driver, case_input, case_number)
            time.sleep(0.25)
    except Exception as e:
        print("Failed to focus/type into case input:", e)
        raise

    # 4. Submit the form (use service helper, then fallback to explicit clicks)
    try:
        print("Submitting search...")
        # Prefer explicit tab submit button if present (more reliable)
        try:
            ts = driver.find_element(By.ID, "tab02Submit")
            driver.execute_script("arguments[0].click();", ts)
            print("Clicked tab02Submit")
        except Exception:
            # Fall back to service helper which handles forms and other cases
            try:
                s._submit_search(driver, case_input)
            except Exception as e:
                print("Submit via service failed, attempting JS button fallback:", e)
                try:
                    submit = driver.find_element(
                        By.XPATH,
                        "//button[@type='submit' or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'search') or contains(@class, 'search')]",
                    )
                    driver.execute_script("arguments[0].click();", submit)
                except Exception as e2:
                    print("All submit attempts failed:", e2)
                    # Final fallback: try pressing Enter in the case input
                    try:
                        print("Final fallback: sending ENTER to input")
                        case_input.send_keys(Keys.ENTER)
                    except Exception as e3:
                        print("Final fallback ENTER failed:", e3)
                        raise

    except Exception as submit_err:
        print("Submit step failed:", submit_err)

    # wait for rows to appear
    rows = []
    for _ in range(15):
        time.sleep(1)
        rows = driver.find_elements(By.XPATH, "//table//tbody//tr")
        if rows:
            break

    print("Rows found:", len(rows))
    if not rows:
        # Retry once: re-activate search tab, re-set inputs, and submit again
        print("No table rows detected on first attempt. Retrying submit once...")
        try:
            # Retry by re-initializing the court-files page and re-running the search
            print("Retry: re-initializing search page")
            s.initialize_page()
            driver = s._get_driver()

            # re-locate visible input
            case_input = None
            for pid in possible_input_ids:
                try:
                    els = driver.find_elements(By.ID, pid)
                    for el in els:
                        if el.is_displayed() and el.is_enabled():
                            case_input = el
                            break
                    if case_input:
                        break
                except Exception:
                    continue

            # re-set court select
            for sid in possible_select_ids:
                try:
                    sel = driver.find_element(By.ID, sid)
                    driver.execute_script(
                        "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change'));",
                        sel,
                        "t",
                    )
                    break
                except Exception:
                    continue

            if case_input is None:
                print("Retry: could not locate case input after re-init")
            else:
                s._safe_send_keys(driver, case_input, case_number)
                time.sleep(0.25)
                try:
                    s._submit_search(driver, case_input)
                except Exception:
                    try:
                        case_input.send_keys(Keys.ENTER)
                    except Exception:
                        pass

            # wait again for rows
            rows = []
            for _ in range(12):
                time.sleep(1)
                rows = driver.find_elements(By.XPATH, "//table//tbody//tr")
                if rows:
                    break
        except Exception as retry_err:
            print("Retry attempt failed:", retry_err)

        if not rows:
            print("No table rows detected. Saving diagnostics.")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"logs/auto_click_more_no_rows_{ts}.png")
        with open(
            f"logs/auto_click_more_no_rows_{ts}.html", "w", encoding="utf-8"
        ) as f:
            f.write(driver.page_source)
        raise SystemExit("No rows")

    # find row where first cell contains the case number
    target_row = None
    for r in rows:
        try:
            first = r.find_element(By.TAG_NAME, "td")
            if case_number in first.text:
                target_row = r
                break
        except Exception:
            continue

    if target_row is None:
        print("Could not locate row with case number; saving diagnostics")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"logs/auto_click_more_no_target_{ts}.png")
        with open(
            f"logs/auto_click_more_no_target_{ts}.html", "w", encoding="utf-8"
        ) as f:
            f.write(driver.page_source)
        raise SystemExit("No matching row")

    print("Found target row. Attempting to locate More control...")
    # Extract summary fields from the result row BEFORE clicking 'More'
    pre_click_case = None
    pre_click_style = None
    pre_click_nature = None
    try:
        # find the enclosing table to read header labels if present
        table = target_row.find_element(By.XPATH, "ancestor::table")
        # attempt to locate header cells
        headers = []
        try:
            headers = [
                h.text.strip().lower()
                for h in table.find_elements(By.XPATH, ".//thead//th")
                if h.text and h.text.strip()
            ]
        except Exception:
            # try first row th fallback
            try:
                headers = [
                    h.text.strip().lower()
                    for h in table.find_elements(By.XPATH, ".//tr[1]/th")
                    if h.text and h.text.strip()
                ]
            except Exception:
                headers = []

        cols = target_row.find_elements(By.TAG_NAME, "td")
        texts = [c.text.strip() for c in cols]

        def get_by_header(names):
            # find index of header matching any of the names
            for n in names:
                for i, h in enumerate(headers):
                    if n in h:
                        if i < len(texts):
                            return texts[i]
            return None

        # header name candidates
        pre_click_case = get_by_header(
            ["court file", "court number", "court no", "court file no", "court number"]
        ) or (texts[0] if len(texts) > 0 else None)
        pre_click_style = get_by_header(
            ["style", "style of cause", "style of cause/"]
        ) or (texts[1] if len(texts) > 1 else None)
        pre_click_nature = get_by_header(["nature", "nature of proceeding"]) or (
            texts[2] if len(texts) > 2 else None
        )

        print("Pre-click extracted:")
        print("  case:", pre_click_case)
        print("  style_of_cause:", pre_click_style)
        print("  nature_of_proceeding:", pre_click_nature)
    except Exception as e:
        print("Pre-click extraction failed:", e)
    # Try several selectors within the row to find the 'More' control
    # Prefer explicit 're' then 'more' id, then fa-search-plus icon (green), then fallbacks.
    candidate_xpaths = [
        ".//button[@id='re']",
        ".//a[@id='re']",
        ".//button[@id='more']",
        ".//a[@id='more']",
        ".//button[.//i[contains(@class,'fa-search-plus')]]",
        ".//a[.//i[contains(@class,'fa-search-plus')]]",
        ".//button[.//i[contains(@class,'fa-search')]]",
        ".//a[.//i[contains(@class,'fa-search')]]",
        ".//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')]",
        ".//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')]",
        ".//button[contains(@data-target, 'Modal') or contains(@data-toggle, 'modal')]",
        ".//a[contains(@href, 'javascript') or contains(@href, '#') or contains(@data-target, 'Modal')]",
    ]

    more_el = None
    for xp in candidate_xpaths:
        try:
            more_el = target_row.find_element(By.XPATH, xp)
            print("Found More element via:", xp)
            break
        except Exception:
            continue

    if more_el is None:
        # Try any clickable element in the last column, preferring fa-search-plus
        try:
            last_col = target_row.find_elements(By.TAG_NAME, "td")[-1]
            try:
                more_el = last_col.find_element(
                    By.XPATH,
                    ".//button[.//i[contains(@class,'fa-search-plus')]] | .//a[.//i[contains(@class,'fa-search-plus')]]",
                )
            except Exception:
                more_el = last_col.find_element(By.XPATH, ".//a | .//button")
            print("Found More element in last column")
        except Exception:
            more_el = None

    if more_el is None:
        print("No More control found; saving diagnostics")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"logs/auto_click_more_no_more_{ts}.png")
        with open(
            f"logs/auto_click_more_no_more_{ts}.html", "w", encoding="utf-8"
        ) as f:
            f.write(driver.page_source)
        raise SystemExit("No More control")

    # Click More
    try:
        more_el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", more_el)

    # wait for modal content
    modal = None
    for _ in range(10):
        time.sleep(1)
        try:
            modal = driver.find_element(
                By.XPATH,
                "//div[@id='ModalForm']//div[contains(@class,'modal-content')] | //div[contains(@class,'modal-content')]",
            )
            if modal and modal.is_displayed():
                break
        except Exception:
            modal = None
            continue

    if modal is None:
        print("Modal did not appear; saving diagnostics")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"logs/auto_click_more_no_modal_{ts}.png")
        with open(
            f"logs/auto_click_more_no_modal_{ts}.html", "w", encoding="utf-8"
        ) as f:
            f.write(driver.page_source)
        raise SystemExit("No modal")

    # Pause briefly and allow user to visually confirm modal contents.
    print("Modal appeared. Pausing 5 seconds for you to inspect...")
    time.sleep(5)
    if non_interactive:
        print("Non-interactive mode — continuing without waiting for Enter.")
    else:
        try:
            input(
                "If the modal looks correct, press Enter to continue with extraction (or Ctrl-C to abort)..."
            )
        except Exception:
            # In non-interactive runs, just continue
            pass

    # Use service internal extractors to parse modal
    case_data = s._extract_case_header(modal)
    # Merge pre-click extracted values into modal header when modal lacks them
    try:
        if not case_data.get("case_id") and pre_click_case:
            case_data["case_id"] = pre_click_case
        if not case_data.get("style_of_cause") and pre_click_style:
            case_data["style_of_cause"] = pre_click_style
        if not case_data.get("nature_of_proceeding") and pre_click_nature:
            case_data["nature_of_proceeding"] = pre_click_nature
    except Exception:
        pass
    docket_entries = s._extract_docket_entries(modal, case_number)
    # Ensure each entry has the case_id set (defensive)
    for ent in docket_entries:
        try:
            if not getattr(ent, "case_id", None):
                ent.case_id = case_number
        except Exception:
            continue

    print("\nCase data:")
    print(case_data)
    print("\nDocket entries count:", len(docket_entries))
    for i, e in enumerate(docket_entries[:20], start=1):
        print(i, e)

    # save modal snapshot
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    driver.save_screenshot(f"logs/auto_click_more_modal_{ts}.png")
    with open(f"logs/auto_click_more_modal_{ts}.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print("Saved modal diagnostics in logs/")

    # Export structured JSON to output/
    try:
        import json
        from pathlib import Path

        out_dir = Path("output")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_case = (case_data.get("case_id") or case_number).replace("/", "_")
        out_path = out_dir / f"{safe_case}_{ts}.json"

        # Normalize case_data dates to ISO
        cd = dict(case_data)
        if isinstance(cd.get("filing_date"), (str,)):
            # assume already iso
            pass
        else:
            try:
                if cd.get("filing_date") is not None:
                    cd["filing_date"] = cd["filing_date"].isoformat()
            except Exception:
                pass

        payload = {
            "case": cd,
            "docket_entries": [
                (
                    e.to_dict()
                    if hasattr(e, "to_dict")
                    else {
                        "doc_id": getattr(e, "doc_id", None),
                        "case_id": getattr(e, "case_id", None),
                        "entry_date": (
                            getattr(e, "entry_date", None).isoformat()
                            if getattr(e, "entry_date", None)
                            else None
                        ),
                        "entry_office": getattr(e, "entry_office", None),
                        "summary": getattr(e, "summary", None),
                    }
                )
                for e in docket_entries
            ],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

        with open(out_path, "w", encoding="utf-8") as jf:
            json.dump(payload, jf, ensure_ascii=False, indent=2)
        print(f"Saved structured JSON to {out_path}")
    except Exception as e:
        print("Failed to write JSON output:", e)

    # Close the modal by clicking the Close button inside it
    try:
        # look for common close button variants inside modal
        close_btn = modal.find_element(
            By.XPATH,
            ".//button[@data-dismiss='modal' or contains(., 'Close') or contains(., 'Fermer')]",
        )
        try:
            close_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", close_btn)
        # wait for modal to disappear
        for _ in range(10):
            time.sleep(0.5)
            try:
                if not modal.is_displayed():
                    break
            except Exception:
                break
        print("Modal closed via Close button.")
    except Exception:
        print(
            "Could not find/close modal Close button; attempting to click generic close"
        )
        try:
            generic_close = driver.find_element(
                By.XPATH,
                "//div[@id='ModalForm']//button[contains(@class,'close') or @aria-label='Close'] | //button[contains(., 'Close')]",
            )
            driver.execute_script("arguments[0].click();", generic_close)
        except Exception:
            print("Failed to close modal programmatically.")

    # Allow the user to confirm before exiting and closing browser.
    # If non-interactive mode is enabled, skip the final prompt so the
    # script exits cleanly in non-interactive runs.
    try:
        if non_interactive:
            print("Non-interactive mode — exiting without waiting for Enter.")
        else:
            try:
                input("Press Enter to exit and close the browser...")
            except Exception:
                pass
    except Exception:
        # As a last resort, do not block exit
        pass

finally:
    s.close()
