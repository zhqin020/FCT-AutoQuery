-- Federal Court Scraper Database Schema
-- Database: fct_db
-- User: fct_user

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';
SET default_table_access_method = heap;

--
-- Name: case_analysis; Type: TABLE; Schema: public; Owner: fct_user
--

CREATE TABLE IF NOT EXISTS public.case_analysis (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(50) UNIQUE,
    title TEXT,
    court VARCHAR(100),
    filing_date DATE,
    case_type VARCHAR(50),
    case_status VARCHAR(50),
    visa_office VARCHAR(200),
    judge VARCHAR(200),
    time_to_close INTEGER,
    age_of_case INTEGER,
    rule9_wait INTEGER,
    outcome_date DATE,
    analysis_mode VARCHAR(20) NOT NULL CHECK (analysis_mode IN ('rule', 'llm', 'smart')),
    analysis_version VARCHAR(20) DEFAULT '1.0',
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    analysis_data JSONB,
    original_case_id VARCHAR(50),
    memo_response_time INTEGER,
    memo_to_outcome_time INTEGER,
    reply_memo_time INTEGER,
    reply_to_outcome_time INTEGER,
    doj_memo_date DATE,
    reply_memo_date DATE,
    has_hearing BOOLEAN,
    year INTEGER,
    outcome_entry JSONB
);

--
-- Name: cases; Type: TABLE; Schema: public; Owner: fct_user
--

CREATE TABLE IF NOT EXISTS public.cases (
    case_number VARCHAR(20) PRIMARY KEY,
    case_type VARCHAR(100),
    type_of_action VARCHAR(100),
    nature_of_proceeding TEXT,
    filing_date DATE,
    office VARCHAR(50),
    style_of_cause TEXT,
    language VARCHAR(20),
    html_content TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    last_attempt_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    year INTEGER,
    CONSTRAINT cases_court_file_no_not_null CHECK (case_number IS NOT NULL)
);

--
-- Name: docket_entries; Type: TABLE; Schema: public; Owner: fct_user
--

CREATE TABLE IF NOT EXISTS public.docket_entries (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(20),
    id_from_table INTEGER,
    date_filed DATE,
    office VARCHAR(50),
    recorded_entry_summary TEXT,
    CONSTRAINT docket_entries_court_file_no_id_from_table_key UNIQUE (case_number, id_from_table),
    CONSTRAINT docket_entries_court_file_no_fkey FOREIGN KEY (case_number) REFERENCES public.cases(case_number)
);

--
-- Create indexes for better performance
--

-- case_analysis indexes
CREATE INDEX IF NOT EXISTS idx_case_analysis_analyzed_at ON public.case_analysis USING btree (analyzed_at);
CREATE INDEX IF NOT EXISTS idx_case_analysis_filing_date ON public.case_analysis USING btree (filing_date);
CREATE INDEX IF NOT EXISTS idx_case_analysis_mode ON public.case_analysis USING btree (analysis_mode);
CREATE INDEX IF NOT EXISTS idx_case_analysis_outcome_entry ON public.case_analysis USING gin (outcome_entry);
CREATE INDEX IF NOT EXISTS idx_case_analysis_status ON public.case_analysis USING btree (case_status);
CREATE INDEX IF NOT EXISTS idx_case_analysis_type ON public.case_analysis USING btree (case_type);
CREATE INDEX IF NOT EXISTS idx_case_analysis_visa_office ON public.case_analysis USING btree (visa_office);

-- cases indexes
CREATE INDEX IF NOT EXISTS idx_cases_last_attempt ON public.cases USING btree (last_attempt_at);
CREATE INDEX IF NOT EXISTS idx_cases_retry_count ON public.cases USING btree (retry_count);
CREATE INDEX IF NOT EXISTS idx_cases_status ON public.cases USING btree (status);
CREATE INDEX IF NOT EXISTS idx_cases_year ON public.cases USING btree (year);

-- Grant permissions (will be executed by init script)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO fct_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO fct_user;

COMMENT ON TABLE public.cases IS 'Main table storing federal court case information';
COMMENT ON TABLE public.docket_entries IS 'Docket entries for each case';
COMMENT ON TABLE public.case_analysis IS 'Analyzed case data with calculated metrics';
