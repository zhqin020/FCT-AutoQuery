from typing import Callable, Tuple, Optional
import time

from src.lib.rate_limiter import EthicalRateLimiter


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
        probe_budget: int = 200,
        rate_limiter: Optional[EthicalRateLimiter] = None,
    ) -> Tuple[int, int]:
        """
        Find an approximate upper bound (highest existing numeric id) using
        exponential probing + conservative backward scan + forward refinement.

        Args:
            check_case_exists: callable that accepts an int and returns True if that id exists
            start: starting low bound (inclusive)
            initial_high: initial high guess to begin exponential probing
            max_limit: hard upper limit to avoid runaway
            coarse_step: step for backward coarse scan
            refine_range: forward refinement window size
            probe_budget: maximum number of probes allowed

        Returns:
            (upper_bound, probes_used)
        """
        probes = 0

        low = start
        high = initial_high

        # Exponential growth to find a high that likely does NOT exist
        while True:
            if probes >= probe_budget:
                break
            try:
                exists = check_case_exists(high)
                probes += 1
            except Exception as exc:
                # Treat exceptions from the check as transient; use rate_limiter backoff if available
                if rate_limiter is not None:
                    try:
                        delay = rate_limiter.record_failure()
                    except Exception:
                        delay = 0.1
                    # small sleep to respect backoff
                    time.sleep(delay)
                else:
                    # if no rate limiter, small sleep to avoid tight loop
                    time.sleep(0.1)
                # count this as a probe attempt and continue probing
                probes += 1
                # continue to next iteration
                continue

            if not exists:
                # Double-check a bit further to avoid mistaking a sparse hole for end
                if probes < probe_budget:
                    try:
                        exists_next = check_case_exists(min(high + 50, max_limit))
                        probes += 1
                    except Exception:
                        if rate_limiter is not None:
                            try:
                                delay = rate_limiter.record_failure()
                            except Exception:
                                delay = 0.1
                            time.sleep(delay)
                        else:
                            time.sleep(0.1)
                        probes += 1
                        exists_next = False
                else:
                    exists_next = False

                if not exists_next:
                    break

            # continue expanding
            low = high
            high = min(high * 2, max_limit)
            if high >= max_limit:
                break

        # Coarse backward scan from high down to low to find first existing
        current = high
        final_max = low
        while current > low and probes < probe_budget:
            try:
                exists = check_case_exists(current)
                probes += 1
            except Exception:
                if rate_limiter is not None:
                    try:
                        delay = rate_limiter.record_failure()
                    except Exception:
                        delay = 0.1
                    time.sleep(delay)
                else:
                    time.sleep(0.1)
                probes += 1
                current -= coarse_step
                continue

            if exists:
                final_max = current
                break
            current -= coarse_step

        # Fine-grained forward refinement
        true_end = final_max
        for i in range(final_max, min(final_max + refine_range, max_limit) + 1):
            if probes >= probe_budget:
                break
            try:
                exists = check_case_exists(i)
                probes += 1
            except Exception:
                if rate_limiter is not None:
                    try:
                        delay = rate_limiter.record_failure()
                    except Exception:
                        delay = 0.1
                    time.sleep(delay)
                else:
                    time.sleep(0.1)
                probes += 1
                continue

            if exists:
                true_end = i

        return true_end, probes
