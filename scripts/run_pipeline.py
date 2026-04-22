#!/usr/bin/env python3
"""
CLI entry point for the lead generation pipeline.

Usage:
    python scripts/run_pipeline.py              # live run
    python scripts/run_pipeline.py --dry-run    # log only, no API writes
    python scripts/run_pipeline.py --max-pages 3  # limit Apollo pages (testing)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

# Allow running from the repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Insurance Lead Generation Pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log all actions without calling outreach/CRM APIs",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Override apollo_max_pages from config (useful for testing)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )

    # Override settings before importing pipeline
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
    if args.max_pages:
        os.environ["APOLLO_MAX_PAGES"] = str(args.max_pages)

    from lead_pipeline.pipeline import run  # import after env vars are set

    await run()


if __name__ == "__main__":
    asyncio.run(main())
