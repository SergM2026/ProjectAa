#!/usr/bin/env python3
"""
Start the FastAPI webhook server.

Usage:
    python scripts/run_webhook_server.py
    python scripts/run_webhook_server.py --port 9000 --reload

For production, use gunicorn:
    gunicorn lead_pipeline.webhooks.server:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Webhook Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes (dev only)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    import uvicorn

    uvicorn.run(
        "lead_pipeline.webhooks.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
