#!/usr/bin/env python3
from src.cli.main import FederalCourtScraperCLI

cases = [
    "IMM-33-25",
    "IMM-34-25",
    "IMM-35-25",
    "IMM-36-25",
    "IMM-37-25",
    "IMM-38-25",
]

if __name__ == '__main__':
    cli = FederalCourtScraperCLI()
    for c in cases:
        print(f"Running scrape for {c}")
        res = cli.scrape_single_case(c)
        print(f"Result for {c}: {res is not None}")
    try:
        cli.shutdown()
    except Exception:
        pass
