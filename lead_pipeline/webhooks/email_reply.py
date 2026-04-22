"""
Instantly.ai reply webhook handler.

When a lead replies to a cold email, this module:
  1. Parses the reply event
  2. Fires a Slack alert immediately
  3. Pauses that lead in Instantly so no further emails go out
  4. Updates HubSpot stage to REPLIED and attaches the reply preview as a note
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..crm_sync import add_note, mark_lead_stage, upsert_contact
from ..models import EmailReplyEvent, EmailStatus, Lead, LeadSource
from ..notifications.slack import notify_email_reply
from ..outreach.instantly_client import pause_lead

logger = logging.getLogger(__name__)


def _parse_reply_event(payload: dict[str, Any]) -> EmailReplyEvent | None:
    """
    Map an Instantly.ai reply webhook payload to our internal model.

    Instantly v2 reply event schema (relevant fields):
    {
      "event_type": "reply_received",
      "data": {
        "lead_email": "...",
        "lead_name": "...",
        "campaign_id": "...",
        "campaign_name": "...",
        "reply_text": "...",
        "timestamp": "2024-01-15T10:30:00Z",
        "thread_id": "..."
      }
    }
    """
    try:
        data = payload.get("data", payload)  # handle both wrapped and flat payloads
        timestamp_raw = data.get("timestamp") or data.get("replied_at") or datetime.utcnow().isoformat()

        return EmailReplyEvent(
            lead_email=data["lead_email"],
            lead_name=data.get("lead_name"),
            campaign_id=data.get("campaign_id", ""),
            campaign_name=data.get("campaign_name"),
            reply_text=data.get("reply_text", data.get("body", "")),
            replied_at=datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00")),
            thread_id=data.get("thread_id"),
        )
    except (KeyError, ValueError) as exc:
        logger.error("Failed to parse Instantly reply payload: %s | payload: %s", exc, payload)
        return None


async def handle_email_reply_event(payload: dict[str, Any]) -> None:
    """Top-level handler — called from the FastAPI route."""
    event = _parse_reply_event(payload)
    if event is None:
        return

    logger.info("Email reply from %s (%s)", event.lead_name or "unknown", event.lead_email)

    # 1. Slack alert — highest priority, do this first
    await notify_email_reply(event)

    # 2. Pause further emails to this lead immediately
    await pause_lead(event.lead_email)

    # 3. Update HubSpot
    stub_lead = Lead(
        first_name=(event.lead_name or "").split()[0] if event.lead_name else "",
        last_name=" ".join((event.lead_name or "").split()[1:]),
        full_name=event.lead_name or event.lead_email,
        email=event.lead_email,  # type: ignore[arg-type]
        title="Prospect",
        source=LeadSource.manual,
        email_status=EmailStatus.valid,
    )
    contact_id = await upsert_contact(stub_lead)

    if contact_id:
        await mark_lead_stage(contact_id, "REPLIED")
        preview = event.reply_text[:500]
        note = (
            f"Lead replied to cold email campaign '{event.campaign_name or event.campaign_id}'.\n"
            f"Reply: {preview}"
        )
        await add_note(contact_id, note)
