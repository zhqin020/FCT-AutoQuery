-- Sample SQL to insert one case and one docket entry for testing
-- Edit values as needed before running.

INSERT INTO cases (court_file_no, case_type, type_of_action, nature_of_proceeding, filing_date, office, style_of_cause, language, html_content, scraped_at)
VALUES (
  'IMM-1-25',
  'Immigration',
  'Judicial Review',
  'Sample nature of proceeding for testing',
  '2025-01-02',
  'Toronto',
  'Sample v. Sample',
  'EN',
  '<html><body>Sample case content</body></html>',
  NOW()
)
ON CONFLICT (court_file_no) DO UPDATE SET
  case_type = EXCLUDED.case_type,
  type_of_action = EXCLUDED.type_of_action,
  nature_of_proceeding = EXCLUDED.nature_of_proceeding,
  filing_date = EXCLUDED.filing_date,
  office = EXCLUDED.office,
  style_of_cause = EXCLUDED.style_of_cause,
  language = EXCLUDED.language,
  html_content = EXCLUDED.html_content,
  scraped_at = EXCLUDED.scraped_at;

-- Insert a docket entry (id_from_table should be unique per case)
INSERT INTO docket_entries (court_file_no, id_from_table, date_filed, office, recorded_entry_summary)
VALUES ('IMM-1-25', 1, '2025-01-03', 'Toronto', 'Initial filing - sample')
ON CONFLICT (court_file_no, id_from_table) DO NOTHING;
