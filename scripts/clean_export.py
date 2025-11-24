"""Utility: Clean JSON export into structured CSVs.

Produces two CSVs from a JSON export containing raw modal HTML:
- cases_clean_{timestamp}.csv -> case-level fields parsed from HTML
- docket_entries_{timestamp}.csv -> one row per docket entry parsed from modal table

This script uses simple HTML regex heuristics (no external deps) suitable for the project's modal structure.
"""

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def text_from_html(html: str) -> str:
    # Remove HTML tags and collapse whitespace
    s = re.sub(r"<script[\s\S]*?<\\/script>", "", html, flags=re.I)
    s = re.sub(r"<style[\s\S]*?<\\/style>", "", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def extract_label_value(html: str, label: str) -> str | None:
    # Look for patterns like '<strong>Label :</strong> VALUE' or 'Label : VALUE'
    # Try several variants
    patterns = [
        rf"{re.escape(label)}\s*[:\u00A0\s]*</?strong>\s*([^<\n]+)",
        rf"<strong>\s*{re.escape(label)}\s*[:\u00A0\s]*<\\/strong>\s*([^<\n]+)",
        rf"{re.escape(label)}\s*[:\u00A0\s]*([^<\n]+)",
    ]
    for p in patterns:
        m = re.search(p, html, flags=re.I)
        if m:
            val = m.group(1)
            val = re.sub(r"&nbsp;", " ", val)
            val = re.sub(r"\s+", " ", val).strip()
            return val
    return None


def extract_docket_entries(html: str):
    # Find the largest table tbody (heuristic) and parse rows
    tbodies = re.findall(r"<tbody>([\s\S]*?)<\\/tbody>", html, flags=re.I)
    if not tbodies:
        return []
    # Pick the tbody with the most <tr>
    best = max(tbodies, key=lambda b: b.count("<tr"))
    rows = re.findall(r"<tr>([\s\S]*?)<\\/tr>", best, flags=re.I)
    entries = []
    for ridx, r in enumerate(rows, start=1):
        # extract td contents
        tds = re.findall(r"<td[^>]*>([\s\S]*?)<\\/td>", r, flags=re.I)
        texts = [text_from_html(td) for td in tds]
        # Heuristic: first column id, second date, third office, rest summary
        if not texts:
            continue
        doc_id = texts[0].strip() or str(ridx)
        entry_date = None
        entry_office = None
        summary = None
        if len(texts) >= 2:
            entry_date = texts[1].strip()
        if len(texts) >= 3:
            entry_office = texts[2].strip()
        if len(texts) >= 4:
            summary = texts[3].strip()
        else:
            # join remaining as summary
            summary = " | ".join(t for t in texts[1:] if t)
        entries.append(
            {
                "doc_id": doc_id,
                "entry_date": entry_date,
                "entry_office": entry_office,
                "summary": summary,
            }
        )
    # Filter out placeholder/example rows if present (e.g., doc_id '#' or 'ID')
    entries = [e for e in entries if e["doc_id"] and e["doc_id"] not in ("#", "ID")]
    return entries


def main(json_path: str):
    p = Path(json_path)
    if not p.exists():
        print(f"JSON file not found: {json_path}")
        sys.exit(1)

    data = json.loads(p.read_text(encoding="utf-8"))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = p.parent
    cases_csv = out_dir / f"cases_clean_{ts}.csv"
    entries_csv = out_dir / f"docket_entries_{ts}.csv"

    with (
        open(cases_csv, "w", encoding="utf-8", newline="") as cf,
        open(entries_csv, "w", encoding="utf-8", newline="") as ef,
    ):
        cwriter = csv.writer(cf)
        ewriter = csv.writer(ef)

        cwriter.writerow(
            [
                "case_id",
                "title",
                "case_type",
                "action_type",
                "nature_of_proceeding",
                "filing_date",
                "office",
                "language",
                "url",
                "scraped_at",
            ]
        )
        ewriter.writerow(["case_id", "doc_id", "entry_date", "entry_office", "summary"])

        for item in data:
            case_id = item.get("case_id") or item.get("case_number")
            html = item.get("html_content", "") or ""
            scraped_at = item.get("scraped_at")
            # try to extract labels
            case_type = (
                extract_label_value(html, "Type")
                or extract_label_value(html, "Type of action")
                or item.get("case_type")
            )
            action_type = extract_label_value(html, "Type of Action") or item.get(
                "action_type"
            )
            nature = extract_label_value(html, "Nature of Proceeding") or item.get(
                "nature_of_proceeding"
            )
            filing_date = extract_label_value(html, "Filing Date") or item.get(
                "filing_date"
            )
            office = extract_label_value(html, "Office") or item.get("office")
            language = extract_label_value(html, "Language") or item.get("language")
            title = item.get("title") or item.get("style_of_cause")

            cwriter.writerow(
                [
                    case_id,
                    title,
                    case_type or "",
                    action_type or "",
                    nature or "",
                    filing_date or "",
                    office or "",
                    language or "",
                    item.get("url") or "",
                    scraped_at or "",
                ]
            )

            # parse docket entries
            entries = extract_docket_entries(html)
            for e in entries:
                ewriter.writerow(
                    [
                        case_id,
                        e["doc_id"] or "",
                        e["entry_date"] or "",
                        e["entry_office"] or "",
                        e["summary"] or "",
                    ]
                )

    print(f"Wrote cleaned case CSV: {cases_csv}")
    print(f"Wrote docket entries CSV: {entries_csv}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/clean_export.py <json_export_path>")
        sys.exit(1)
    main(sys.argv[1])
