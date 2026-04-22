#!/usr/bin/env python3
"""
Pre-flight check — verifies all API keys are valid before a live run.

Usage:
    python scripts/verify_setup.py

Exit code 0 = all checks passed. Exit code 1 = one or more failures.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET}  {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET}  {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET}  {msg}")


async def check_apollo(api_key: str) -> bool:
    print("\n[Apollo.io]")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.apollo.io/v1/auth/health",
                json={"api_key": api_key},
                timeout=10.0,
            )
        if resp.status_code == 200:
            ok("API key valid")
            return True
        fail(f"HTTP {resp.status_code}: {resp.text[:120]}")
        return False
    except Exception as exc:
        fail(f"Connection error: {exc}")
        return False


async def check_zerobounce(api_key: str) -> bool:
    print("\n[ZeroBounce]")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.zerobounce.net/v2/getcredits",
                params={"api_key": api_key},
                timeout=10.0,
            )
        if resp.status_code == 200:
            credits = resp.json().get("Credits", 0)
            ok(f"API key valid — {credits} credits remaining")
            if int(credits) < 100:
                warn("Low ZeroBounce credits — consider topping up before a full run.")
            return True
        fail(f"HTTP {resp.status_code}: {resp.text[:120]}")
        return False
    except Exception as exc:
        fail(f"Connection error: {exc}")
        return False


async def check_hubspot(access_token: str) -> bool:
    print("\n[HubSpot]")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.hubapi.com/crm/v3/objects/contacts?limit=1",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
        if resp.status_code == 200:
            ok("Access token valid")
            return True
        fail(f"HTTP {resp.status_code}: {resp.text[:120]}")
        return False
    except Exception as exc:
        fail(f"Connection error: {exc}")
        return False


async def check_slack(webhook_url: str) -> bool:
    print("\n[Slack]")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                webhook_url,
                json={"text": ":white_check_mark: Lead pipeline setup verified successfully."},
                timeout=10.0,
            )
        if resp.status_code == 200:
            ok("Webhook valid — test message sent to Slack channel")
            return True
        fail(f"HTTP {resp.status_code}: {resp.text}")
        return False
    except Exception as exc:
        fail(f"Connection error: {exc}")
        return False


async def check_instantly(api_key: str, campaign_id: str) -> bool:
    print("\n[Instantly.ai]")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.instantly.ai/api/v2/campaigns/{campaign_id}",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
        if resp.status_code == 200:
            name = resp.json().get("name", campaign_id)
            ok(f"Campaign found: '{name}'")
            return True
        fail(f"HTTP {resp.status_code}: {resp.text[:120]}")
        return False
    except Exception as exc:
        fail(f"Connection error: {exc}")
        return False


async def main() -> None:
    print("=" * 55)
    print("  Insurance Lead Pipeline — Setup Verification")
    print("=" * 55)

    from lead_pipeline.config import settings

    results = await asyncio.gather(
        check_apollo(settings.apollo_api_key),
        check_zerobounce(settings.zerobounce_api_key),
        check_hubspot(settings.hubspot_access_token),
        check_slack(settings.slack_webhook_url),
        check_instantly(settings.instantly_api_key, settings.instantly_campaign_id),
    )

    passed = sum(results)
    total = len(results)
    print(f"\n{'='*55}")
    print(f"  Result: {passed}/{total} checks passed")
    print("=" * 55)

    if passed < total:
        print(f"\n{RED}Fix the failing checks above before running the pipeline.{RESET}\n")
        sys.exit(1)
    else:
        print(f"\n{GREEN}All checks passed — you're ready to run the pipeline!{RESET}\n")
        print("  Next steps:")
        print("  1.  python scripts/run_pipeline.py --dry-run   (smoke test)")
        print("  2.  python scripts/run_pipeline.py             (live run)")
        print("  3.  python scripts/run_webhook_server.py       (start webhook server)")
        print()


if __name__ == "__main__":
    asyncio.run(main())
