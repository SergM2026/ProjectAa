"""
Expandi.io LinkedIn outreach client.

Expandi is a cloud-based LinkedIn automation tool that respects
LinkedIn's daily connection and message limits to minimize ban risk.

Key safety guardrails built into Expandi (configured in their dashboard):
  - Max 20 connection requests / day (LinkedIn's safe threshold)
  - Delays randomized between actions (2–15 minutes)
  - Activity only during business hours in the lead's timezone
  - Auto-pause when LinkedIn login challenge is detected

Expandi API docs: https://help.expandi.io/en/articles/6029990-expandi-api

NOTE: LinkedIn scraping without authorization violates LinkedIn's ToS.
      This integration ONLY sends connection requests to people you have
      found through legitimate means (Apollo.io licensed data) and uses
      Expandi's managed sending infrastructure.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import settings
from ..models import Lead

logger = logging.getLogger(__name__)

_BASE = "https://api.expandi.io"


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.expandi_api_key}",
        "Content-Type": "application/json",
    }


async def add_lead_to_campaign(lead: Lead) -> bool:
    """
    Add a lead to an Expandi LinkedIn outreach campaign.

    The campaign must already be configured in the Expandi dashboard with:
      - Connection request message template (under 300 chars)
      - Follow-up message sequence (after connection accepted)
      - Daily limits set to ≤20 connection requests

    Returns True on success or dry-run.
    """
    if not lead.linkedin_url:
        logger.debug(
            "Skipping Expandi enroll for %s — no LinkedIn URL.", lead.full_name
        )
        return False

    if settings.dry_run:
        logger.info(
            "[DRY RUN] Would add %s (%s) to Expandi campaign.",
            lead.full_name,
            lead.linkedin_url,
        )
        return True

    payload: dict[str, Any] = {
        "campaign_id": settings.expandi_campaign_id,
        "linkedin_url": str(lead.linkedin_url),
        "custom_variables": {
            "first_name": lead.first_name,
            "title": lead.title,
            "company": lead.company or "",
            "city": lead.city or "Utah",
            # Used inside the Expandi message template as {{connection_note}}
            "connection_note": _build_connection_note(lead),
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_BASE}/api/campaigns/{settings.expandi_campaign_id}/leads",
            headers=_auth_headers(),
            json=payload,
            timeout=15.0,
        )

    if resp.status_code in (200, 201):
        logger.info("Expandi: queued %s for LinkedIn outreach.", lead.full_name)
        return True
    elif resp.status_code == 409:
        logger.debug("Expandi: %s already in campaign.", lead.full_name)
        return True
    else:
        logger.error("Expandi enroll failed for %s: %s", lead.full_name, resp.text)
        return False


async def add_leads_bulk(leads: list[Lead]) -> int:
    """Enroll a list of leads into Expandi. Returns count of successes."""
    success = 0
    for lead in leads:
        if await add_lead_to_campaign(lead):
            success += 1
    logger.info(
        "Expandi bulk enroll: %d/%d leads queued for LinkedIn outreach.",
        success,
        len(leads),
    )
    return success


def _build_connection_note(lead: Lead) -> str:
    """
    Personalized LinkedIn connection request note (≤ 300 characters).

    This text maps to {{connection_note}} in your Expandi template.
    Keep it conversational, NOT salesy — goal is just to connect.
    """
    note = (
        f"Hi {lead.first_name}, I work with {lead.title}s in Utah on business "
        f"insurance tailored to your industry. Would love to connect!"
    )
    # LinkedIn hard cap is 300 characters
    return note[:300]
