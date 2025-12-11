from typing import Callable, Tuple, Optional
import time
import random
import signal

from src.lib.rate_limiter import EthicalRateLimiter
from src.lib.config import Config
from src.lib.logging_config import get_logger
import json
from pathlib import Path

logger = get_logger()

def _timeout_handler(signum, frame):
    raise TimeoutError("Scrape timeout")

# Set up timeout signal handler
signal.signal(signal.SIGALRM, _timeout_handler)


class BatchService:
    """Services for batch operations like upper-bound probing."""

    @staticmethod
    def exponential_probe_and_collect(
        check_case_exists: Callable[[int], bool],
        fast_check_case_exists: Optional[Callable[[int], dict]] = None,
        start: int = 0,
        max_exponent: Optional[int] = None,
        rate_limiter: Optional[EthicalRateLimiter] = None,
        check_retries: int = 1,
        check_retry_delay: float = 0.5,
        scrape_case_data: Optional[Callable[[int], Optional[object]]] = None,
        max_cases: int = 100000,
        format_case_number: Optional[Callable[[int], str]] = None,
        safe_stop: Optional[int] = None,
    ) -> Tuple[int, int, list]:
        """
        Find an approximate upper bound using exponential probing while collecting case data.

        Args:
            check_case_exists: callable that accepts an int and returns True if that id exists
            start: starting number
            max_exponent: maximum exponent for 2^i steps
            scrape_case_data: callable to scrape case data (always enabled)
            max_cases: maximum number of cases to collect

        Returns:
            (upper_bound, probes_used, collected_cases)
        """
        probes = 0
        collected_cases = []
        collected_count = 0

        safe_stop = Config.get_safe_stop_no_records() if safe_stop is None else int(safe_stop)
        if max_exponent is None:
            max_exponent = Config.get_max_exponent()

        # Formatter for numeric id to readable case_id (e.g. IMM-5-21)
        if format_case_number is None:
            fmt = lambda n: str(n)
        else:
            fmt = format_case_number

        # Track probes to avoid duplicate checks and to record state
        visited: dict[int, bool] = {}

        # Try to load persisted probe-state to avoid rechecking previously probed ids
        probe_state_path = Config.get_probe_state_file() if Config.get_persist_probe_state() else None
        if probe_state_path:
            try:
                ppath = Path(probe_state_path)
                if ppath.exists():
                    try:
                        with ppath.open("r", encoding="utf-8") as fh:
                            raw = json.load(fh)
                            # raw is expected to be mapping of str(id) -> bool
                            for k, v in raw.items():
                                try:
                                    visited[int(k)] = bool(v)
                                except Exception:
                                    continue
                        logger.info(f"Loaded probe-state from {ppath} ({len(visited)} entries)")
                    except Exception as e:
                        logger.debug(f"Failed to load probe-state {ppath}: {e}")
            except Exception:
                probe_state_path = None

        current_start = start
        last_success = None
        consecutive_no_data = 0
        i = 0
        last_success_position = None
        rounds = 0

        # Exponential probing phase with looping
        while True:
            rounds += 1
            if rounds > 100:
                logger.warning(f"Reached max probe rounds {rounds}, breaking to prevent infinite loop")
                break
            # Reset for this round
            i = 0
            consecutive_no_data = 0
            last_success_this_round = None

            logger.info(f"Starting exponential probe round {rounds} from {current_start} (probes={probes}, collected={collected_count})")

            # Exponential probing for this segment
            while i <= max_exponent and collected_count < max_cases:
                if i == 0:
                    number = current_start
                else:
                    number = current_start + (1 << (i - 1))
                if number > start + max_cases:
                    logger.debug(f"Number {number} > {start + max_cases}, breaking inner loop")
                    break

                logger.debug(f"Probing i={i}, number={number}, consecutive_no_data={consecutive_no_data}")
                
                # Increment probes counter for each case checked
                probes += 1

                # Check if case exists and its status
                should_scrape = True
                if fast_check_case_exists:
                    status_info = fast_check_case_exists(number)
                    if status_info.get('exists'):
                        if status_info.get('status') == 'success':
                            # Treat as existing data
                            last_success = number
                            last_success_this_round = number
                            consecutive_no_data = 0
                            logger.debug(f"Case {fmt(number)} exists with status success, treating as data")
                            should_scrape = False
                        elif status_info.get('status') == 'no_data':
                            # Treat as no data
                            consecutive_no_data += 1
                            logger.debug(f"Case {fmt(number)} exists with status no_data, treating as no data")
                            should_scrape = False
                        # If status is 'failed', should_scrape remains True to retry

                if should_scrape and scrape_case_data:
                    # Directly attempt to scrape the case data
                    try:
                        case = scrape_case_data(number)
                        if case:
                            collected_count += 1
                            collected_cases.append(case)
                            last_success = number
                            last_success_this_round = number
                            consecutive_no_data = 0
                            logger.info(f"Successfully collected case {fmt(number)} (collected={collected_count})")
                        else:
                            consecutive_no_data += 1
                            logger.debug(f"Case {fmt(number)} not found or failed to scrape")
                    except Exception as e:
                        logger.debug(f"Failed to scrape case {fmt(number)}: {e}")
                        consecutive_no_data += 1

                if consecutive_no_data >= safe_stop:
                    break

                i += 1

                # Periodically save probe state
                if i % 3 == 0 and probe_state_path:
                    try:
                        ppath = Path(probe_state_path)
                        ppath.parent.mkdir(parents=True, exist_ok=True)
                        out = {}
                        if ppath.exists():
                            try:
                                with ppath.open("r", encoding="utf-8") as fh:
                                    out = json.load(fh) or {}
                            except Exception:
                                out = {}
                        for k, v in visited.items():
                            out[str(k)] = bool(v)
                        with ppath.open("w", encoding="utf-8") as fh:
                            json.dump(out, fh, indent=2)
                        logger.debug(f"Periodically saved probe-state to {ppath} ({len(out)} entries)")
                    except Exception as e:
                        logger.debug(f"Failed to periodically persist probe-state: {e}")

            # After inner loop, check if upper bound was found
            if consecutive_no_data >= safe_stop:
                break  # Break outer loop to proceed to linear scan

            # If no upper bound found in this round, update current_start for next round
            if last_success_this_round is not None:
                current_start = last_success_this_round + 1
            else:
                current_start += (1 << max_exponent)
            
            if current_start > start + max_cases:
                break  # Prevent exceeding max_cases boundary

        upper = last_success if last_success is not None else start - 1

        # Persist probe-state (merge with existing file) so subsequent runs can skip checked ids
        try:
            if probe_state_path:
                ppath = Path(probe_state_path)
                ppath.parent.mkdir(parents=True, exist_ok=True)
                out = {}
                if ppath.exists():
                    try:
                        with ppath.open("r", encoding="utf-8") as fh:
                            out = json.load(fh) or {}
                    except Exception:
                        out = {}
                for k, v in visited.items():
                    out[str(k)] = bool(v)
                with ppath.open("w", encoding="utf-8") as fh:
                    json.dump(out, fh, indent=2)
                logger.info(f"Saved probe-state to {ppath} ({len(out)} entries)")
        except Exception as e:
            logger.debug(f"Failed to persist probe-state: {e}")

        return upper, probes, collected_cases
