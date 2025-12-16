-- Database schema for Federal Court Case Scraper
-- Tables: cases, docket_entries

CREATE TABLE IF NOT EXISTS cases (
    court_file_no VARCHAR(20) PRIMARY KEY,
    case_type VARCHAR(100),
    type_of_action VARCHAR(100),
    nature_of_proceeding TEXT,
    filing_date DATE,
    office VARCHAR(50),
    style_of_cause TEXT,
    language VARCHAR(20),
    html_content TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS docket_entries (
    id SERIAL PRIMARY KEY,
    court_file_no VARCHAR(20) REFERENCES cases(court_file_no),
    id_from_table INTEGER,
    date_filed DATE,
    office VARCHAR(50),
    recorded_entry_summary TEXT,
    UNIQUE(court_file_no, id_from_table)
);