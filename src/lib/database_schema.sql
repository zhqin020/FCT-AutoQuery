--
-- PostgreSQL database dump
--

\restrict qApJa7K6AHsXDoXaVsJsss3rNwYJGefNc0NyOF5M7gtJ6O03In2p7Lf4deF577D

-- Dumped from database version 18.1 (Ubuntu 18.1-1.pgdg24.04+2)
-- Dumped by pg_dump version 18.1 (Ubuntu 18.1-1.pgdg24.04+2)

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

CREATE TABLE public.case_analysis (
    id integer NOT NULL,
    case_number character varying(50),
    title text,
    court character varying(100),
    filing_date date,
    case_type character varying(50),
    case_status character varying(50),
    visa_office character varying(200),
    judge character varying(200),
    time_to_close integer,
    age_of_case integer,
    rule9_wait integer,
    outcome_date date,
    analysis_mode character varying(20) NOT NULL,
    analysis_version character varying(20) DEFAULT '1.0'::character varying,
    analyzed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    analysis_data jsonb,
    original_case_id character varying(50),
    memo_response_time integer,
    memo_to_outcome_time integer,
    reply_memo_time integer,
    reply_to_outcome_time integer,
    doj_memo_date date,
    reply_memo_date date,
    has_hearing boolean,
    year integer,
    outcome_entry jsonb,
    CONSTRAINT case_analysis_check CHECK (((analysis_mode)::text = ANY ((ARRAY['rule'::character varying, 'llm'::character varying, 'smart'::character varying])::text[])))
);


ALTER TABLE public.case_analysis OWNER TO fct_user;

--
-- Name: case_analysis_backup; Type: TABLE; Schema: public; Owner: fct_user
--

CREATE TABLE public.case_analysis_backup (
    id integer,
    case_id character varying(50),
    case_number character varying(50),
    title text,
    court character varying(100),
    filing_date date,
    case_type character varying(50),
    case_status character varying(50),
    visa_office character varying(200),
    judge character varying(200),
    time_to_close integer,
    age_of_case integer,
    rule9_wait integer,
    outcome_date date,
    analysis_mode character varying(20),
    analysis_version character varying(20),
    analyzed_at timestamp without time zone,
    analysis_data jsonb,
    original_case_id character varying(50),
    memo_response_time integer,
    memo_to_outcome_time integer,
    reply_memo_time integer,
    reply_to_outcome_time integer,
    doj_memo_date date,
    reply_memo_date date,
    has_hearing boolean,
    year integer,
    outcome_entry jsonb
);


ALTER TABLE public.case_analysis_backup OWNER TO fct_user;

--
-- Name: case_analysis_id_seq; Type: SEQUENCE; Schema: public; Owner: fct_user
--

CREATE SEQUENCE public.case_analysis_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.case_analysis_id_seq OWNER TO fct_user;

--
-- Name: case_analysis_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: fct_user
--

ALTER SEQUENCE public.case_analysis_id_seq OWNED BY public.case_analysis.id;


--
-- Name: cases; Type: TABLE; Schema: public; Owner: fct_user
--

CREATE TABLE public.cases (
    case_number character varying(20) CONSTRAINT cases_court_file_no_not_null NOT NULL,
    case_type character varying(100),
    type_of_action character varying(100),
    nature_of_proceeding text,
    filing_date date,
    office character varying(50),
    style_of_cause text,
    language character varying(20),
    html_content text,
    scraped_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    status character varying(20) DEFAULT 'pending'::character varying,
    last_attempt_at timestamp without time zone,
    retry_count integer DEFAULT 0,
    error_message text,
    year integer
);


ALTER TABLE public.cases OWNER TO fct_user;

--
-- Name: docket_entries; Type: TABLE; Schema: public; Owner: fct_user
--

CREATE TABLE public.docket_entries (
    id integer NOT NULL,
    case_number character varying(20),
    id_from_table integer,
    date_filed date,
    office character varying(50),
    recorded_entry_summary text
);


ALTER TABLE public.docket_entries OWNER TO fct_user;

--
-- Name: docket_entries_id_seq; Type: SEQUENCE; Schema: public; Owner: fct_user
--

CREATE SEQUENCE public.docket_entries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.docket_entries_id_seq OWNER TO fct_user;

--
-- Name: docket_entries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: fct_user
--

ALTER SEQUENCE public.docket_entries_id_seq OWNED BY public.docket_entries.id;


--
-- Name: case_analysis id; Type: DEFAULT; Schema: public; Owner: fct_user
--

ALTER TABLE ONLY public.case_analysis ALTER COLUMN id SET DEFAULT nextval('public.case_analysis_id_seq'::regclass);


--
-- Name: docket_entries id; Type: DEFAULT; Schema: public; Owner: fct_user
--

ALTER TABLE ONLY public.docket_entries ALTER COLUMN id SET DEFAULT nextval('public.docket_entries_id_seq'::regclass);


--
-- Name: case_analysis case_analysis_case_number_uq; Type: CONSTRAINT; Schema: public; Owner: fct_user
--

ALTER TABLE ONLY public.case_analysis
    ADD CONSTRAINT case_analysis_case_number_uq UNIQUE (case_number);


--
-- Name: case_analysis case_analysis_pkey; Type: CONSTRAINT; Schema: public; Owner: fct_user
--

ALTER TABLE ONLY public.case_analysis
    ADD CONSTRAINT case_analysis_pkey PRIMARY KEY (id);


--
-- Name: cases cases_pkey; Type: CONSTRAINT; Schema: public; Owner: fct_user
--

ALTER TABLE ONLY public.cases
    ADD CONSTRAINT cases_pkey PRIMARY KEY (case_number);


--
-- Name: docket_entries docket_entries_court_file_no_id_from_table_key; Type: CONSTRAINT; Schema: public; Owner: fct_user
--

ALTER TABLE ONLY public.docket_entries
    ADD CONSTRAINT docket_entries_court_file_no_id_from_table_key UNIQUE (case_number, id_from_table);


--
-- Name: docket_entries docket_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: fct_user
--

ALTER TABLE ONLY public.docket_entries
    ADD CONSTRAINT docket_entries_pkey PRIMARY KEY (id);


--
-- Name: idx_case_analysis_analyzed_at; Type: INDEX; Schema: public; Owner: fct_user
--

CREATE INDEX idx_case_analysis_analyzed_at ON public.case_analysis USING btree (analyzed_at);


--
-- Name: idx_case_analysis_filing_date; Type: INDEX; Schema: public; Owner: fct_user
--

CREATE INDEX idx_case_analysis_filing_date ON public.case_analysis USING btree (filing_date);


--
-- Name: idx_case_analysis_mode; Type: INDEX; Schema: public; Owner: fct_user
--

CREATE INDEX idx_case_analysis_mode ON public.case_analysis USING btree (analysis_mode);


--
-- Name: idx_case_analysis_outcome_entry; Type: INDEX; Schema: public; Owner: fct_user
--

CREATE INDEX idx_case_analysis_outcome_entry ON public.case_analysis USING gin (outcome_entry);


--
-- Name: idx_case_analysis_status; Type: INDEX; Schema: public; Owner: fct_user
--

CREATE INDEX idx_case_analysis_status ON public.case_analysis USING btree (case_status);


--
-- Name: idx_case_analysis_type; Type: INDEX; Schema: public; Owner: fct_user
--

CREATE INDEX idx_case_analysis_type ON public.case_analysis USING btree (case_type);


--
-- Name: idx_case_analysis_visa_office; Type: INDEX; Schema: public; Owner: fct_user
--

CREATE INDEX idx_case_analysis_visa_office ON public.case_analysis USING btree (visa_office);


--
-- Name: idx_cases_last_attempt; Type: INDEX; Schema: public; Owner: fct_user
--

CREATE INDEX idx_cases_last_attempt ON public.cases USING btree (last_attempt_at);


--
-- Name: idx_cases_retry_count; Type: INDEX; Schema: public; Owner: fct_user
--

CREATE INDEX idx_cases_retry_count ON public.cases USING btree (retry_count);


--
-- Name: idx_cases_status; Type: INDEX; Schema: public; Owner: fct_user
--

CREATE INDEX idx_cases_status ON public.cases USING btree (status);


--
-- Name: idx_cases_year; Type: INDEX; Schema: public; Owner: fct_user
--

CREATE INDEX idx_cases_year ON public.cases USING btree (year);


--
-- Name: docket_entries docket_entries_court_file_no_fkey; Type: FK CONSTRAINT; Schema: public; Owner: fct_user
--

ALTER TABLE ONLY public.docket_entries
    ADD CONSTRAINT docket_entries_court_file_no_fkey FOREIGN KEY (case_number) REFERENCES public.cases(case_number);



--
-- PostgreSQL database dump complete
--

\unrestrict qApJa7K6AHsXDoXaVsJsss3rNwYJGefNc0NyOF5M7gtJ6O03In2p7Lf4deF577D

