"""
Instantly.ai cold email outreach client.

Adds verified leads to an Instantly campaign and exposes a reply-
webhook parser used by the FastAPI server.

Instantly API v2 docs: https://developer.instantly.ai/
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import settings
from ..models import Lead

logger = logging.getLogger(__name__)

_BASE = "https://api.instantly.ai/api/v2"


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.instantly_api_key}",
        "Content-Type": "application/json",
    }


async def add_lead_to_campaign(lead: Lead) -> bool:
    """
    Enroll a single lead in the configured Instantly campaign.
    Returns True on success.

    Instantly uses the lead's email as the primary key — duplicate
    emails in the same campaign are silently deduplicated by Instantly.
    """
    if not lead.email:
        logger.warning("Skipping Instantly enroll for %s — no email.", lead.full_name)
        return False

    if settings.dry_run:
        logger.info("[DRY RUN] Would add %s <%s> to Instantly campaign.", lead.full_name, lead.email)
        return True

    payload: dict[str, Any] = {
        "campaign_id": settings.instantly_campaign_id,
        "email": str(lead.email),
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "company_name": lead.company or "",
        "personalization": _build_personalization(lead),
        "custom_variables": {
            "title": lead.title,
            "city": lead.city or "Utah",
            "linkedin_url": str(lead.linkedin_url) if lead.linkedin_url else "",
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_BASE}/leads",
            headers=_auth_headers(),
            json=payload,
            timeout=15.0,
        )

    if resp.status_code in (200, 201):
        logger.info("Instantly: enrolled %s <%s>", lead.full_name, lead.email)
        return True
    elif resp.status_code == 409:
        logger.debug("Instantly: %s already in campaign.", lead.email)
        return True
    else:
        logger.error("Instantly enroll failed for %s: %s", lead.email, resp.text)
        return False


async def add_leads_bulk(leads: list[Lead]) -> int:
    """Enroll a list of leads. Returns count of successful enrollments."""
    success = 0
    for lead in leads:
        if await add_lead_to_campaign(lead):
            success += 1
    logger.info("Instantly bulk enroll: %d/%d leads queued.", success, len(leads))
    return success


def _build_personalization(lead: Lead) -> str:
    """
    Generates a one-sentence personalization snippet injected into the
    first email of the sequence via the {{personalization}} variable.

    Example: "As a CPA in Salt Lake City, protecting your practice from
    E&O and cyber liability is mission-critical..."
    """
    city_phrase = f"in {lead.city}" if lead.city else "in Utah"
    title_phrase = lead.title

    return (
        f"As a {title_phrase} {city_phrase}, protecting your practice from "
        f"E&O and cyber liability is mission-critical for your clients and your business"
    )


async def pause_lead(email: str) -> bool:
    """Remove a lead from active sending (e.g., after opt-out or reply)."""
    if settings.dry_run:
        logger.info("[DRY RUN] Would pause %s in Instantly.", email)
        return True

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{_BASE}/leads",
            headers=_auth_headers(),
            json={
                "campaign_id": settings.instantly_campaign_id,
                "email": email,
                "lead_status": 1,  # 1 = paused in Instantly v2
            },
            timeout=15.0,
        )
    return resp.status_code in (200, 204)
