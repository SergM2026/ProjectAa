"""
ZeroBounce email verification.

Validates a batch of leads and tags each one with an EmailStatus so
downstream systems never attempt to send to dead addresses. Invalid
and do-not-mail addresses are filtered before outreach is triggered.

ZeroBounce docs: https://www.zerobounce.net/docs/
Batch endpoint accepts up to 200 emails per call.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import settings
from .models import EmailStatus, Lead

logger = logging.getLogger(__name__)

_ZB_BATCH_URL = "https://bulkapi.zerobounce.net/v2/validatebatch"
_ZB_CREDITS_URL = "https://api.zerobounce.net/v2/getcredits"
_BATCH_SIZE = 200

# ZeroBounce status strings → our internal enum
_STATUS_MAP: dict[str, EmailStatus] = {
    "valid": EmailStatus.valid,
    "invalid": EmailStatus.invalid,
    "catch-all": EmailStatus.catch_all,
    "unknown": EmailStatus.unknown,
    "spamtrap": EmailStatus.do_not_mail,
    "abuse": EmailStatus.do_not_mail,
    "do_not_mail": EmailStatus.do_not_mail,
}

# Statuses we consider safe to email
MAILABLE_STATUSES = {EmailStatus.valid, EmailStatus.catch_all}


async def _check_credits(client: httpx.AsyncClient) -> int:
    resp = await client.get(
        _ZB_CREDITS_URL,
        params={"api_key": settings.zerobounce_api_key},
        timeout=10.0,
    )
    resp.raise_for_status()
    return int(resp.json().get("Credits", 0))


async def _verify_batch(
    client: httpx.AsyncClient,
    emails: list[str],
) -> dict[str, EmailStatus]:
    """Verify up to 200 emails and return {email: status} mapping."""
    payload = {
        "api_key": settings.zerobounce_api_key,
        "email_batch": [{"email_address": e} for e in emails],
    }
    resp = await client.post(_ZB_BATCH_URL, json=payload, timeout=60.0)
    resp.raise_for_status()

    results: dict[str, EmailStatus] = {}
    for item in resp.json().get("email_batch", []):
        email_addr: str = item.get("address", "").lower()
        zb_status: str = item.get("status", "unknown").lower()
        results[email_addr] = _STATUS_MAP.get(zb_status, EmailStatus.unknown)

    return results


async def verify_leads(leads: list[Lead]) -> list[Lead]:
    """
    Mutate each lead's email_status in-place using ZeroBounce.

    Leads without an email address are left with EmailStatus.unknown.
    Returns the same list (mutated) so callers can chain: leads = await verify_leads(leads).
    """
    emailable = [lead for lead in leads if lead.email]
    if not emailable:
        logger.info("No leads with email addresses to verify.")
        return leads

    async with httpx.AsyncClient() as client:
        credits = await _check_credits(client)
        logger.info("ZeroBounce credits remaining: %d", credits)
        if credits < len(emailable):
            logger.warning(
                "Insufficient ZeroBounce credits (%d) for %d emails — skipping verification.",
                credits,
                len(emailable),
            )
            return leads

        # Build a quick lookup for mutation
        lead_by_email: dict[str, Lead] = {
            str(lead.email).lower(): lead for lead in emailable
        }

        # Process in batches of 200
        email_list = list(lead_by_email.keys())
        for i in range(0, len(email_list), _BATCH_SIZE):
            batch = email_list[i : i + _BATCH_SIZE]
            statuses = await _verify_batch(client, batch)
            for email_addr, status in statuses.items():
                if email_addr in lead_by_email:
                    lead_by_email[email_addr].email_status = status

            logger.info(
                "ZeroBounce: verified batch %d–%d of %d",
                i + 1,
                min(i + _BATCH_SIZE, len(email_list)),
                len(email_list),
            )
            # Brief pause between batches
            if i + _BATCH_SIZE < len(email_list):
                await asyncio.sleep(0.5)

    valid_count = sum(1 for l in leads if l.email_status in MAILABLE_STATUSES)
    logger.info(
        "Verification complete — %d/%d leads have mailable addresses.",
        valid_count,
        len(emailable),
    )
    return leads


def filter_mailable(leads: list[Lead]) -> list[Lead]:
    """Return only leads whose email address passed verification."""
    return [l for l in leads if l.email_status in MAILABLE_STATUSES]
