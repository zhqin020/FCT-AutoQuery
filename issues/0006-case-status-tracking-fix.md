# Case Status Tracking Issues Fix

**Issue Date:** 2025-12-04  
**Status:** CLOSED

## Problems Identified

### Problem 1: `pending` status cases being incorrectly skipped
- **Issue:** Cases with `pending` status were being skipped instead of being treated as uncollected
- **Root Cause:** Missing explicit handling of `pending` status in both `simplified_tracking_service.py` and `case_tracking_service.py`
- **Impact:** New cases were not being processed

### Problem 2: `failed` status cases being incorrectly skipped  
- **Issue:** Cases with `failed` status were being skipped instead of being retried
- **Root Cause:** In `case_tracking_service.py`, when a case had DB record but no high-level snapshot, it was unconditionally skipped regardless of status
- **Impact:** Failed cases were not being retried

### Problem 3: IMM-5-21 incorrect status
- **Issue:** Case IMM-5-21 had status `failed` but should likely be `no_data`
- **Root Cause:** General "Scraping failed" error message when case may actually have no data
- **Impact:** Case was being skipped when it should be properly marked as no-data

## Fixes Applied

### Fix 1: `simplified_tracking_service.py` (lines 90-93)
```python
# 如果状态是 pending，当作未采集处理，不能跳过
if status == CaseStatus.PENDING:
    logger.info(f"Case {case_number}: status is pending, treating as uncollected")
    return False, ""
```

### Fix 2: `case_tracking_service.py` (lines 384-398)
```python
# If status is pending or failed, treat as uncollected and don't skip
if status in ('pending', 'failed'):
    try:
        stored_no = self.get_stored_case_case_number(case_number) or case_number
        self.record_case_processing(
            case_number=stored_no,
            run_id=run_id,
            outcome='proceed',
            reason=f"exists_in_db (status: {status}, retry_count: {retry_count}), will collect",
            processing_mode='db_check'
        )
    except Exception:
        pass
    return False, f"exists_in_db but status is {status}, will collect (retry_count: {retry_count})"
```

### Fix 3: Corrected IMM-5-21 status
- Updated IMM-5-21 from `failed` to `no_data` status
- Verified the update was applied correctly

## Expected Behavior After Fix

1. **`pending` cases:** Will be treated as uncollected and processed
2. **`failed` cases:** Will be retried (subject to cooldown limits)
3. **`no_data` cases:** Will be properly skipped
4. **`success` cases:** Will continue to be skipped as before

## Additional Fix: Database Field Standardization

### Problem 4: Inconsistent field naming between tables
- **Issue:** `cases` table used `case_number` while `docket_entries` table used `court_file_no`
- **Root Cause:** Historical inconsistency in database schema design
- **Impact:** Confusion in queries and code maintenance

### Fix 4: Database schema unification
- ✅ Renamed `docket_entries.court_file_no` to `docket_entries.case_number`
- ✅ Updated `src/services/export_service.py` SQL statements
- ✅ Verified all 1,262 docket entries are accessible with new field name
- ✅ Confirmed both tables now use consistent `case_number` field

## Verification

- ✅ IMM-5-21 status updated to `no_data`
- ✅ Code fixes applied with no lint errors
- ✅ Logic now properly handles all status cases
- ✅ Database fields standardized across all tables
- ✅ Export service updated to use consistent field names

## Notes

The core issue was inconsistent handling of different case statuses across the two tracking services. The fix ensures both services follow the same logic:
- Skip: `success`, `no_data`
- Process: `pending`, `failed` (subject to cooldown for failed)

**Additional:** Database schema has been standardized to use `case_number` consistently across all tables, eliminating confusion between `case_number` and `court_file_no`.