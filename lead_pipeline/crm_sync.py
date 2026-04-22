"""
HubSpot CRM sync.

Creates or updates contacts in HubSpot and records outreach activity
as timeline events so the full lead journey is visible in the CRM.

Uses HubSpot's v3 Contacts API with the private-app token auth model
(no OAuth dance required for single-portal use).

HubSpot docs: https://developers.hubspot.com/docs/api/crm/contacts
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import settings
from .models import Lead, OutreachChannel

logger = logging.getLogger(__name__)

_HS_BASE = "https://api.hubapi.com"
_HEADERS = {
    "Authorization": f"Bearer {settings.hubspot_access_token}",
    "Content-Type": "application/json",
}

# HubSpot property names → our field names
_PROP_MAP = {
    "firstname": "first_name",
    "lastname": "last_name",
    "email": "email",
    "phone": "phone",
    "jobtitle": "title",
    "company": "company",
    "website": "company_website",
    "city": "city",
    "state": "state",
    "linkedinbio": "linkedin_url",
}


def _build_properties(lead: Lead) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for hs_prop, field in _PROP_MAP.items():
        value = getattr(lead, field, None)
        if value is not None:
            props[hs_prop] = str(value)
    props["lead_source"] = lead.source.value
    props["hs_lead_status"] = "NEW"
    return props


async def upsert_contact(lead: Lead) -> str | None:
    """
    Create or update a HubSpot contact for the given lead.
    Returns the HubSpot contact ID on success, None on failure.
    Stores the contact ID back on the lead object.
    """
    if not lead.email:
        logger.warning("Skipping HubSpot upsert for %s — no email.", lead.full_name)
        return None

    properties = _build_properties(lead)

    async with httpx.AsyncClient() as client:
        # Try to find existing contact by email first
        search_payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "email",
                            "operator": "EQ",
                            "value": str(lead.email),
                        }
                    ]
                }
            ],
            "properties": ["hs_object_id", "email"],
            "limit": 1,
        }
        search_resp = await client.post(
            f"{_HS_BASE}/crm/v3/objects/contacts/search",
            headers=_HEADERS,
            json=search_payload,
            timeout=15.0,
        )

        if search_resp.status_code == 200:
            results = search_resp.json().get("results", [])
            if results:
                contact_id = results[0]["id"]
                # Update existing contact
                patch_resp = await client.patch(
                    f"{_HS_BASE}/crm/v3/objects/contacts/{contact_id}",
                    headers=_HEADERS,
                    json={"properties": properties},
                    timeout=15.0,
                )
                if patch_resp.status_code in (200, 204):
                    lead.hubspot_contact_id = contact_id
                    logger.info("HubSpot: updated contact %s (%s)", contact_id, lead.email)
                    return contact_id
                else:
                    logger.warning("HubSpot update failed: %s", patch_resp.text)
                    return None

        # Create new contact
        create_resp = await client.post(
            f"{_HS_BASE}/crm/v3/objects/contacts",
            headers=_HEADERS,
            json={"properties": properties},
            timeout=15.0,
        )
        if create_resp.status_code == 201:
            contact_id = create_resp.json()["id"]
            lead.hubspot_contact_id = contact_id
            logger.info("HubSpot: created contact %s (%s)", contact_id, lead.email)
            return contact_id
        elif create_resp.status_code == 409:
            # Already exists (race condition) — extract the ID from the error body
            existing_id = (
                create_resp.json()
                .get("message", "")
                .split("Existing ID: ")[-1]
                .strip()
            )
            lead.hubspot_contact_id = existing_id or None
            return existing_id or None
        else:
            logger.error(
                "HubSpot create failed for %s: %s", lead.email, create_resp.text
            )
            return None


async def upsert_contacts_bulk(leads: list[Lead]) -> int:
    """
    Upsert a list of leads into HubSpot.
    Returns the count of successfully synced contacts.
    """
    success = 0
    for lead in leads:
        contact_id = await upsert_contact(lead)
        if contact_id:
            success += 1
    logger.info("HubSpot bulk upsert: %d/%d contacts synced.", success, len(leads))
    return success


async def add_note(contact_id: str, note_body: str) -> bool:
    """Attach a plain-text note to a HubSpot contact."""
    async with httpx.AsyncClient() as client:
        engagement_payload = {
            "properties": {
                "hs_note_body": note_body,
                "hs_timestamp": str(int(__import__("time").time() * 1000)),
            },
            "associations": [
                {
                    "to": {"id": contact_id},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": 202,
                        }
                    ],
                }
            ],
        }
        resp = await client.post(
            f"{_HS_BASE}/crm/v3/objects/notes",
            headers=_HEADERS,
            json=engagement_payload,
            timeout=15.0,
        )
        success = resp.status_code == 201
        if not success:
            logger.warning("HubSpot note creation failed: %s", resp.text)
        return success


async def mark_lead_stage(contact_id: str, stage: str) -> bool:
    """Update hs_lead_status on a contact (e.g., 'BOOKED', 'REPLIED')."""
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{_HS_BASE}/crm/v3/objects/contacts/{contact_id}",
            headers=_HEADERS,
            json={"properties": {"hs_lead_status": stage}},
            timeout=15.0,
        )
        return resp.status_code in (200, 204)
