# Research Findings

## Decisions Made

**Decision**: Use Python 3.11 with Selenium for browser automation, PostgreSQL for data storage, and JSON for backup files.  
**Rationale**: Existing framework already implements this stack successfully. Selenium handles dynamic content and modal dialogs effectively for the Federal Court website. PostgreSQL provides reliable storage with UPSERT capabilities for resume-on-interrupt. JSON backup ensures data integrity.  
**Alternatives Considered**: 
- Scrapy: Considered for potentially better performance, but Selenium required for JavaScript-heavy modal interactions.
- SQLite: Considered for simplicity, but PostgreSQL chosen for production requirements.
- Direct API calls: Not available from the court website, requiring browser simulation.

**Decision**: Implement rate limiting with random delays (3-6 seconds) and pauses every 100 queries.  
**Rationale**: Prevents detection and blocking by the website. Existing implementation already includes this.  
**Alternatives Considered**: Fixed delays, but random delays provide better camouflage.

**Decision**: Use database-backed tracking for resume capability instead of NDJSON logging.  
**Rationale**: More reliable and allows complex queries for status tracking. Existing code has been migrated to this approach.  
**Alternatives Considered**: File-based tracking, but database provides better concurrency and querying.

## Resolved Clarifications

All technical unknowns have been resolved through existing implementation analysis. No additional research required.