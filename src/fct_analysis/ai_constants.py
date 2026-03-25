"""Shared constants for AI-based case analysis (Local LLM and Aifree API)."""

AI_JSON_SCHEMA = '''{
    "case_id": "IMM-1-24", // Docket number from the document (e.g. IMM-####-##)
    "case_type": "Mandamus", // Options: Mandamus, Judicial Review, Other
    "case_status": "Closed", // Options: Closed, On-Going
    "judgment_result": "granted", // Options: granted, dismiss, leave_granted, leave_dismissed
    "hearing": true, // boolean: Whether a personal appearance/hearing occurred
    "visa_office": "Beijing", // string or null
    "judge": "Justice Pentney", // string or null
    "nature": "Other Arising in Canada", // string or null
    "confidence": "high", // Options: high, medium, low
    "timeline": {
        "filing_date": "2024-07-31", // Application filing date (YYYY-MM-DD)
        "appearance_date": "2024-08-09", // Respondent (DOJ) files Notice of Appearance
        "applicant_record": "2024-09-19", // Applicant files Application Record
        "doj_memo": "2024-10-11", // Respondent (DOJ) files Application Record/Memorandum
        "reply_memo": "2024-10-21", // Applicant submits Reply Memorandum
        "referral_to_judiciary": "2024-11-11", // The Registry passing the file to the Judge
        "leave_grant_date": "2025-02-07", // Court grants leave for judicial review
        "leave_dismissal_date": "2025-02-07", // Court dismisses leave if have
        "certified_record": "2025-02-26", // IRCC sends certified record (pursuant to Court order)
        "hearing_date": "2025-05-01", // Date of the oral hearing (Zoom or personal appearance)
        "judgment_date": "2025-05-01" // Final judgment/decision date
    }
}'''

AI_SYSTEM_PROMPT = "Extract the specified legal status, judgment result, visa office, judge, and key timeline nodes from the provided case data. Return the result strictly as a single JSON object matching the following schema: <ret_json_template>. Deliver only the JSON with no additional commentary. Use null for fields that cannot be extracted."
