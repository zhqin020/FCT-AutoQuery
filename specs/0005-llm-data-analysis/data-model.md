# Data Model and Representative Inputs: llm-data-analysis (0005)

## Purpose
This document defines the canonical input and output data shapes for the `llm-data-analysis` feature and provides representative JSON snippets (including examples of "Rule 9" events) to use as fixtures for tests and parser development.

## Canonical Input (exporter JSON)
This project writes case exports using `ExportService.export_to_json()` which calls `Case.to_dict()` on scraper `Case` objects. The canonical input for downstream analysis should therefore be the JSON structure produced by that export: an array of case dictionaries with these keys (example subset):

- `case_id` / `case_number` (string) — court file number
- `title` / `style_of_cause` (string) — case title
- `court` / `office` (string) — office or court name
- `date` / `filing_date` (string, ISO) — filing date when available
- `case_type`, `action_type`, `nature_of_proceeding` (strings|null)
- `url` (string|null)
- `html_content` (string) — scraped HTML blob
- `scraped_at` (string, ISO) — timestamp when scraped
- `docket_entries` (array) — list of docket entry dicts; each entry follows `DocketEntry.to_dict()` shape:
  - `id` (number|null)
  - `case_id` (string)
  - `doc_id` (number)
  - `entry_date` (string|null, ISO)
  - `entry_office` (string|null)
  - `summary` (string|null)

Note: downstream parsers should be built to accept this exporter shape. If your tests previously used a different structure (for example `events` + `docket_text`), convert or map those fixtures to this canonical exporter format to remain compatible with `cli/main.py` and `ExportService`.

## Canonical Output Record (normalized)
After parsing and enrichment, each output record should contain at minimum:

- `case_number` (string)
- `filing_date` (ISO 8601, YYYY-MM-DD)
- `last_event_date` (ISO 8601)
- `case_type` (string) — e.g., "Mandamus", "Immigration", "Habeas"
- `case_status` (string) — e.g., "Open", "Closed", "Pending"
- `visa_office` (string|null) — from LLM enrichment when available
- `judge` (string|null) — from LLM enrichment when available
- `time_to_close_days` (number|null)
- `age_of_case_days` (number|null)
- `rule9_wait_days` (number|null) — days between Rule 9 event and disposition (if applicable)
- `source_file` (string|null)

## Rule 9 and Event Examples
"Rule 9" in this project refers to a docket event that indicates referral, stay, or administrative step commonly labelled in various ways in raw dockets. Implementations should treat the following as possible Rule 9 indicators (case-insensitive):

- "Rule 9"; "Rule 9 notice"; "rule 9"; "r.9"; "r. 9"
- "referred to immigration" (contextual)
- "order to show cause" (contextual — may require LLM disambiguation)

When computing `rule9_wait_days`, find the earliest event whose text matches the Rule 9 indicators, record its date as `rule9_date`, then compute days until disposition/closure if a closing event exists; otherwise null.

## Representative Inputs (matches `Case.to_dict()` / exported JSON)

Below is an example of one exported case object (the fixture file contains an array of similar objects). Fields like `docket_entries` map from the scraper's internal docket entry model.

{
  "case_id": "IMM-2-23",
  "case_number": "IMM-2-23",
  "title": "SEYEDAMIRHOSSEIN SHEKARABI v. THE MINISTER OF CITIZENSHIP AND IMMIGRATION",
  "court": "Toronto",
  "date": "2023-01-02",
  "case_type": "Immigration Matters",
  "action_type": "Immigration Matters",
  "nature_of_proceeding": "Imm - Appl. for leave & jud. review - Arising outside Canada",
  "filing_date": "2023-01-02",
  "office": "Toronto",
  "style_of_cause": "SEYEDAMIRHOSSEIN SHEKARABI v. THE MINISTER OF CITIZENSHIP AND IMMIGRATION",
  "language": "English",
  "url": "https://www.fct-cf.ca/en/court-files-and-decisions/court-files",
  "html_content": "",
  "scraped_at": "2025-11-26T22:59:01.973633",
  "docket_entries": [
    {"id": null, "case_id": "IMM-2-23", "doc_id": 1, "entry_date": "2023-03-22", "entry_office": "Toronto", "summary": "Solicitor's certificate of service on behalf of Ali Lotfi confirming service of doc. #6 upon Respondent by e-mail on 22-MAR-2023 filed on 22-MAR-2023"},
    {"id": null, "case_id": "IMM-2-23", "doc_id": 2, "entry_date": "2023-03-22", "entry_office": "Toronto", "summary": "Notice of discontinuance on behalf of the applicant filed on 22-MAR-2023"},
    {"id": null, "case_id": "IMM-2-23", "doc_id": 3, "entry_date": "2023-03-15", "entry_office": "Toronto", "summary": "Solicitor's certificate of service on behalf of Ali Lotfi confirming service of Doc 4 upon Respondent by email on 15-MAR-2023 filed on 15-MAR-2023"},
    {"id": null, "case_id": "IMM-2-23", "doc_id": 4, "entry_date": "2023-03-15", "entry_office": "Toronto", "summary": "Application Record Number of copies received/prepared: 1 on behalf of Applicant filed on 15-MAR-2023"},
    {"id": null, "case_id": "IMM-2-23", "doc_id": 5, "entry_date": "2023-02-13", "entry_office": "Ottawa", "summary": "Certified copy of the decision and reasons sent by IRCC Case Processing Center - Ottawa on 07-FEB-2023 pursuant to Rule 9(2) Received on 13-FEB-2023"},
    {"id": null, "case_id": "IMM-2-23", "doc_id": 6, "entry_date": "2023-01-17", "entry_office": "Toronto", "summary": "Notice of appearance on behalf of the respondent filed on 17-JAN-2023 with proof of service on the applicant the tribunal"},
    {"id": null, "case_id": "IMM-2-23", "doc_id": 7, "entry_date": "2023-01-03", "entry_office": "Toronto", "summary": "Acknowledgment of Receipt received from Respondent with respect to doc 1 filed on 03-JAN-2023"},
    {"id": null, "case_id": "IMM-2-23", "doc_id": 8, "entry_date": "2023-01-03", "entry_office": "Toronto", "summary": "Application for leave and judicial review against a decision Embassy of Canada, Turkey, 23-nov-2022, S305500767 filed on 03-JAN-2023 Written reasons not received by the Applicant Tariff fee of $50.00 received"}
  ]
}

Notes:
- Parsers should be defensive: `docket_entries` may be empty; implementations should fallback to `html_content` or `style_of_cause` where appropriate, but must not assume alternative case shapes.
- Use the provided `IMM-*` style fixtures in `tests/fixtures/0005_cases.json` as canonical inputs for unit and integration tests.

## Implementation Guidance
- Date parsing: use `dateutil.parser.parse` (or pandas `to_datetime`) with `errors='coerce'` and fallbacks; record parse failures.
- Text matching: initial rule-mode should use case-insensitive regex matching for keywords (Mandamus, compel, delay) and Rule 9 patterns. LLM-mode should be used when pattern matching is ambiguous or fields are not present.
- LLM prompts: when extracting `judge` or `visa_office` from long text, send only the minimal context (trim long docs) and instruct the model to reply with JSON `{ "judge": "...", "visa_office": "..." }`.
