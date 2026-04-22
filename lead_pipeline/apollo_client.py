"""
Apollo.io People Search API client.

Pulls CPAs and Financial Planners located in Utah using Apollo's
/people/search endpoint with job-title and geo filters.

Apollo docs: https://apolloio.github.io/apollo-api-docs/
Rate limit: 1 req/s on Growth plan; this client respects that with a
configurable delay between pages.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from .config import settings
from .models import EmailStatus, Lead, LeadSource

logger = logging.getLogger(__name__)

_APOLLO_BASE = "https://api.apollo.io/v1"
_SEARCH_ENDPOINT = f"{_APOLLO_BASE}/mixed_people/search"

# Seconds to wait between paginated requests — stay under Apollo rate limits
_PAGE_DELAY_SECONDS = 1.2


def _parse_lead(person: dict[str, Any]) -> Lead | None:
    """Map an Apollo person object to our internal Lead model."""
    try:
        email = person.get("email") or None
        linkedin_raw = person.get("linkedin_url") or None

        return Lead(
            first_name=person.get("first_name", ""),
            last_name=person.get("last_name", ""),
            full_name=person.get("name", ""),
            email=email,
            phone=person.get("phone_numbers", [{}])[0].get("raw_number")
            if person.get("phone_numbers")
            else None,
            title=person.get("title", ""),
            company=person.get("organization", {}).get("name") if person.get("organization") else None,
            company_website=person.get("organization", {}).get("website_url")
            if person.get("organization")
            else None,
            city=person.get("city"),
            state=person.get("state"),
            linkedin_url=linkedin_raw,  # type: ignore[arg-type]
            source=LeadSource.apollo,
            email_status=EmailStatus.unknown,
            apollo_id=person.get("id"),
        )
    except Exception as exc:
        logger.warning("Failed to parse Apollo person record: %s", exc)
        return None


async def _fetch_page(
    client: httpx.AsyncClient,
    page: int,
    title_filter: list[str],
    state: str,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch one page of results; return (records, total_count)."""
    payload = {
        "api_key": settings.apollo_api_key,
        "page": page,
        "per_page": settings.apollo_page_size,
        "person_titles": title_filter,
        # Apollo uses US state names for geo filtering
        "person_locations": [f"{state}, United States"],
        # Only return contacts with a known email
        "contact_email_status": ["verified", "likely_to_engage", "guessed"],
        "sort_by_field": "person_name",
        "sort_ascending": True,
    }

    resp = await client.post(
        _SEARCH_ENDPOINT,
        json=payload,
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()

    people = data.get("people") or data.get("contacts") or []
    pagination = data.get("pagination", {})
    total = pagination.get("total_entries", len(people))
    return people, total


async def fetch_leads(
    title_filter: list[str] | None = None,
    state: str | None = None,
    max_pages: int | None = None,
) -> list[Lead]:
    """
    Pull leads from Apollo matching the configured title + state filters.

    Returns a deduplicated list of Lead objects (deduped on apollo_id / email).
    """
    titles = title_filter or settings.target_titles
    target_state = state or settings.target_state
    pages = max_pages or settings.apollo_max_pages

    leads: list[Lead] = []
    seen_ids: set[str] = set()

    async with httpx.AsyncClient() as client:
        for page_num in range(1, pages + 1):
            try:
                people, total = await _fetch_page(client, page_num, titles, target_state)
            except httpx.HTTPStatusError as exc:
                logger.error("Apollo API error on page %d: %s", page_num, exc)
                break

            if not people:
                logger.info("Apollo returned empty page %d — stopping.", page_num)
                break

            for person in people:
                lead = _parse_lead(person)
                if lead is None:
                    continue
                dedup_key = lead.apollo_id or lead.email
                if dedup_key and dedup_key in seen_ids:
                    continue
                if dedup_key:
                    seen_ids.add(dedup_key)
                leads.append(lead)

            logger.info(
                "Apollo page %d/%d — fetched %d records, running total: %d (of %d)",
                page_num,
                pages,
                len(people),
                len(leads),
                total,
            )

            # Respect rate limit and stop early when all results are fetched
            max_possible_page = -(-total // settings.apollo_page_size)
            if page_num >= max_possible_page:
                break

            await asyncio.sleep(_PAGE_DELAY_SECONDS)

    logger.info("Apollo fetch complete — %d unique leads collected.", len(leads))
    return leads
