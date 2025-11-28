import pytest

from src.services.batch_service import BatchService


def test_find_upper_bound_dense_sequence():
    # Simulate existing ids up to 5600
    max_existing = 5600

    def exists(n: int) -> bool:
        return n <= max_existing

    upper, probes = BatchService.find_upper_bound(
        check_case_exists=exists,
        start=1,
        initial_high=100,
        max_limit=100000,
        coarse_step=100,
        refine_range=200,
        probe_budget=1000,
    )

    assert upper == max_existing
    assert probes <= 1000


def test_find_upper_bound_sparse_holes():
    # Simulate a sparse distribution with final cluster ending at 1002
    existing = set([10, 20, 30, 1000, 1001, 1002])

    def exists(n: int) -> bool:
        return n in existing

    upper, probes = BatchService.find_upper_bound(
        check_case_exists=exists,
        start=1,
        # make the initial high large enough to probe into the 1000+ region
        initial_high=2000,
        max_limit=5000,
        coarse_step=25,
        refine_range=50,
        probe_budget=500,
    )

    assert upper == 1002
    assert probes <= 500


def test_find_upper_bound_respects_probe_budget():
    # Make an oracle that would continue expanding if allowed.
    def exists(n: int) -> bool:
        # Pretend ids below 1_000_000 exist (huge space)
        return n <= 1_000_000

    # Use a tiny budget to ensure the function stops because of budget
    upper, probes = BatchService.find_upper_bound(
        check_case_exists=exists,
        start=0,
        initial_high=100,
        max_limit=10_000_000,
        coarse_step=1000,
        refine_range=1000,
        probe_budget=3,
    )

    assert probes <= 3
    assert isinstance(upper, int)


def test_find_upper_bound_respects_max_limit():
    # All ids up to max_limit exist
    max_limit = 500

    def exists(n: int) -> bool:
        return n <= max_limit

    upper, probes = BatchService.find_upper_bound(
        check_case_exists=exists,
        start=0,
        # ensure initial_high does not exceed max_limit for predictable behavior
        initial_high=100,
        max_limit=max_limit,
        coarse_step=50,
        refine_range=100,
        probe_budget=1000,
    )

    # Should not exceed the configured max_limit
    assert upper <= max_limit
    assert probes <= 1000
