from typing import Callable, Tuple


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
            exists = check_case_exists(high)
            probes += 1
            if not exists:
                # Double-check a bit further to avoid mistaking a sparse hole for end
                if probes < probe_budget:
                    exists_next = check_case_exists(min(high + 50, max_limit))
                    probes += 1
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
            exists = check_case_exists(current)
            probes += 1
            if exists:
                final_max = current
                break
            current -= coarse_step

        # Fine-grained forward refinement
        true_end = final_max
        for i in range(final_max, min(final_max + refine_range, max_limit) + 1):
            if probes >= probe_budget:
                break
            exists = check_case_exists(i)
            probes += 1
            if exists:
                true_end = i

        return true_end, probes
