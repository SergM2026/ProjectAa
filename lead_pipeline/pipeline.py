"""
Main pipeline orchestration.

Run once (e.g., via cron or GitHub Actions) to:
  1. Pull CPAs + Financial Planners in Utah from Apollo
  2. Verify emails with ZeroBounce
  3. Sync verified leads to HubSpot
  4. Enroll in Instantly.ai email campaign
  5. Enroll in Expandi.io LinkedIn campaign
  6. Post a summary to Slack

Typical schedule: run 2–3× per week so LinkedIn and email campaigns
never receive faster than Expandi's daily limit can absorb.
"""
from __future__ import annotations

import asyncio
import logging

from .apollo_client import fetch_leads
from .config import settings
from .crm_sync import upsert_contacts_bulk
from .enrichment import filter_mailable, verify_leads
from .notifications.slack import notify_pipeline_summary
from .outreach.expandi_client import add_leads_bulk as expandi_bulk
from .outreach.instantly_client import add_leads_bulk as instantly_bulk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    logger.info(
        "Pipeline starting — target: %s %s | dry_run=%s",
        settings.target_titles,
        settings.target_state,
        settings.dry_run,
    )

    # ── Step 1: Lead sourcing ──────────────────────────────────────────────────
    leads = await fetch_leads()
    if not leads:
        logger.warning("No leads returned from Apollo — exiting.")
        return
    logger.info("Fetched %d leads from Apollo.", len(leads))

    # ── Step 2: Email verification ─────────────────────────────────────────────
    leads = await verify_leads(leads)
    mailable = filter_mailable(leads)
    logger.info(
        "Verification complete — %d/%d leads have mailable addresses.",
        len(mailable),
        len(leads),
    )

    # ── Step 3: HubSpot CRM sync ───────────────────────────────────────────────
    hubspot_count = await upsert_contacts_bulk(leads)  # sync ALL leads to CRM

    # ── Step 4: Instantly.ai email enroll ─────────────────────────────────────
    email_count = await instantly_bulk(mailable)

    # ── Step 5: Expandi LinkedIn enroll ───────────────────────────────────────
    linkedin_leads = [l for l in leads if l.linkedin_url]
    linkedin_count = await expandi_bulk(linkedin_leads)

    # ── Step 6: Slack summary ─────────────────────────────────────────────────
    await notify_pipeline_summary(
        leads_fetched=len(leads),
        leads_verified=len(mailable),
        email_enrolled=email_count,
        linkedin_enrolled=linkedin_count,
        hubspot_synced=hubspot_count,
    )

    logger.info("Pipeline run complete.")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
