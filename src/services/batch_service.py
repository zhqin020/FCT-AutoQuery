from typing import Callable, Tuple, Optional
import time
import random

from src.lib.rate_limiter import EthicalRateLimiter
from src.lib.config import Config
from src.lib.logging_config import get_logger
import json
from pathlib import Path

logger = get_logger()


class BatchService:
    """Services for batch operations like upper-bound probing."""

    @staticmethod
    def find_upper_bound(
        check_case_exists: Callable[[int], bool],
        start: int = 0,
        initial_high: int = 1000,
        max_limit: int = 100000,
        coarse_step: int = 100,
        refine_range: int = 200,
        probe_budget: int = 10,
        max_probes: int = 10000,
        rate_limiter: Optional[EthicalRateLimiter] = None,
        check_retries: int = 1,
        check_retry_delay: float = 0.5,
        collect: bool = False,
        scrape_case_data: Optional[Callable[[int], Optional[object]]] = None,
        max_cases: int = 100000,
    ) -> Tuple[int, int]:
        """
        Find an approximate upper bound using exponential probing with backtracking.

        Args:
            check_case_exists: callable that accepts an int and returns True if that id exists
            start: starting number
            max_limit: hard upper limit
            probe_budget: maximum i for 2^i steps
            max_probes: maximum number of probes allowed
            collect: if True, scrape data when case exists (for batch mode)
            scrape_case_data: callable to scrape case data if collect=True
            max_cases: maximum number of cases to collect in collect mode

        Returns:
            (upper_bound, probes_used)
        """
        probes = 0
        collected_count = 0

        safe_stop = Config.get_safe_stop_no_records()

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
        last_success_position = None  # 记录最近一次成功的位置
        
        # 第一次指数探测
        while i <= probe_budget and probes < max_probes and (not collect or collected_count < max_cases):
            if i == 0:
                number = current_start
            else:
                number = current_start + (1 << (i - 1))
            if number > max_limit:
                break
            

            
            # 随机延时，模拟人类操作，避免封IP
            delay_min = Config.get_probe_delay_min()
            delay_max = Config.get_probe_delay_max()
            if delay_max > 0:
                time.sleep(random.uniform(delay_min, delay_max))
            
            if number in visited:
                exists = visited[number]
            else:
                attempt = 0
                exists = False
                while attempt <= check_retries and probes < max_probes:
                    try:
                        exists = check_case_exists(number)
                        probes += 1
                        break
                    except Exception as e:
                        attempt += 1
                        probes += 1
                        logger.warning(f"Attempt {attempt} failed for {number}: {e}")

                        if rate_limiter is not None:
                            try:
                                delay = rate_limiter.record_failure()
                            except Exception:
                                delay = check_retry_delay
                            time.sleep(delay)
                        else:
                            time.sleep(check_retry_delay)
                visited[number] = exists
                logger.info(f"Probing {number}: {exists} (probes={probes}, collected={collected_count})")

            if exists:
                last_success = number
                last_success_position = i  # 记录成功时的i位置
                consecutive_no_data = 0
                if collect and scrape_case_data:
                    try:
                        case = scrape_case_data(number)
                        if case:
                            collected_count += 1
                    except Exception as e:
                        logger.debug(f"Failed to scrape case {number}: {e}")
            else:
                consecutive_no_data += 1
                if consecutive_no_data >= safe_stop:
                    # 进入第二次扫描
                    if last_success_position is not None and last_success_position > 0:
                        # 回到最近一次成功位置
                        previous_i = last_success_position
                        if previous_i == 0:
                            previous_number = current_start
                        else:
                            previous_number = current_start + (1 << (previous_i - 1))
                        logger.info(f"Starting second scan from {previous_number} after {consecutive_no_data} consecutive no-data results")
                        # 重置状态，开始第二次扫描
                        current_start = previous_number
                        last_success = previous_number if previous_number in visited and visited[previous_number] else last_success
                        consecutive_no_data = 0
                        i = 0
                        last_success_position = None
                        continue
                    break

            i += 1

            # Periodically save probe state to handle interruptions
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
                    # merge visited into out (string keys)
                    for k, v in visited.items():
                        out[str(k)] = bool(v)
                    with ppath.open("w", encoding="utf-8") as fh:
                        json.dump(out, fh, indent=2)
                    logger.debug(f"Periodically saved probe-state to {ppath} ({len(out)} entries)")
                except Exception as e:
                    logger.debug(f"Failed to periodically persist probe-state: {e}")

        upper = last_success if last_success is not None else start - 1

        # Do linear scan from last_success +1 to find exact upper
        if last_success is not None:
            current = last_success + 1
            consecutive_no_data_linear = 0
            while current <= max_limit and probes < max_probes and (not collect or collected_count < max_cases):
                # 随机延时，模拟人类操作，避免封IP
                delay_min = Config.get_probe_delay_min()
                delay_max = Config.get_probe_delay_max()
                if delay_max > 0:
                    time.sleep(random.uniform(delay_min, delay_max))
                
                if current in visited:
                    exists = visited[current]
                else:
                    attempt = 0
                    exists = False
                    while attempt <= check_retries and probes < max_probes:
                        try:
                            exists = check_case_exists(current)
                            probes += 1
                            break
                        except Exception as e:
                            attempt += 1
                            probes += 1
                            logger.warning(f"Linear scan attempt {attempt} failed for {current}: {e}")
                            if rate_limiter is not None:
                                try:
                                    delay = rate_limiter.record_failure()
                                except Exception:
                                    delay = check_retry_delay
                                time.sleep(delay)
                            else:
                                time.sleep(check_retry_delay)
                    visited[current] = exists
                    logger.info(f"Linear scan {current}: {exists} (probes={probes}, collected={collected_count})")
                if exists:
                    upper = current
                    consecutive_no_data_linear = 0
                    if collect and scrape_case_data:
                        try:
                            case = scrape_case_data(current)
                            if case:
                                collected_count += 1
                        except Exception as e:
                            logger.debug(f"Failed to scrape case {current}: {e}")
                else:
                    consecutive_no_data_linear += 1
                    if consecutive_no_data_linear >= safe_stop:
                        break
                current += 1
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
                # merge visited into out (string keys)
                for k, v in visited.items():
                    out[str(k)] = bool(v)
                with ppath.open("w", encoding="utf-8") as fh:
                    json.dump(out, fh, indent=2)
                logger.info(f"Saved probe-state to {ppath} ({len(out)} entries)")
        except Exception as e:
            logger.debug(f"Failed to persist probe-state: {e}")

        return upper, probes
