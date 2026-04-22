"""
Slack notification module.

Posts rich Block Kit messages to a Slack channel via an Incoming Webhook
URL. Two event types are supported:
  - Email reply received (from Instantly.ai)
  - Appointment booked  (from Calendly)

Slack Block Kit builder: https://app.slack.com/block-kit-builder
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from ..config import settings
from ..models import BookingEvent, EmailReplyEvent

logger = logging.getLogger(__name__)


async def _post(blocks: list[dict[str, Any]], fallback_text: str) -> bool:
    """Send a Block Kit payload to the configured Slack webhook."""
    payload = {
        "text": fallback_text,  # shown in notifications & screen-reader mode
        "blocks": blocks,
        "channel": settings.slack_channel,
        "username": "Insurance Lead Pipeline",
        "icon_emoji": ":briefcase:",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            settings.slack_webhook_url,
            json=payload,
            timeout=10.0,
        )

    if resp.status_code == 200 and resp.text == "ok":
        return True

    logger.error("Slack notification failed: HTTP %s — %s", resp.status_code, resp.text)
    return False


async def notify_email_reply(event: EmailReplyEvent) -> bool:
    """Post a 'lead replied to cold email' alert."""
    ts = event.replied_at.strftime("%b %d, %Y at %I:%M %p UTC")
    preview = event.reply_text[:300] + "…" if len(event.reply_text) > 300 else event.reply_text

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📬 New Email Reply from Lead",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Lead:*\n{event.lead_name or 'Unknown'}"},
                {"type": "mrkdwn", "text": f"*Email:*\n{event.lead_email}"},
                {"type": "mrkdwn", "text": f"*Campaign:*\n{event.campaign_name or event.campaign_id}"},
                {"type": "mrkdwn", "text": f"*Replied At:*\n{ts}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Reply Preview:*\n>{preview}",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View in Instantly", "emoji": True},
                    "url": f"https://app.instantly.ai/app/campaigns/{event.campaign_id}",
                    "style": "primary",
                },
            ],
        },
        {"type": "divider"},
    ]

    return await _post(
        blocks,
        fallback_text=f"New email reply from {event.lead_name or event.lead_email}",
    )


async def notify_booking(event: BookingEvent) -> bool:
    """Post an 'appointment booked' alert."""
    start = event.start_time.strftime("%A, %b %d at %I:%M %p UTC")
    end = event.end_time.strftime("%I:%M %p UTC")

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🗓️ New Appointment Booked!",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Name:*\n{event.invitee_name}"},
                {"type": "mrkdwn", "text": f"*Email:*\n{event.invitee_email}"},
                {"type": "mrkdwn", "text": f"*Meeting:*\n{event.event_name}"},
                {"type": "mrkdwn", "text": f"*When:*\n{start} – {end}"},
            ],
        },
    ]

    if event.meeting_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Join Meeting", "emoji": True},
                        "url": str(event.meeting_url),
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reschedule", "emoji": True},
                        "url": str(event.reschedule_url) if event.reschedule_url else "#",
                    },
                ],
            }
        )

    blocks.append({"type": "divider"})

    return await _post(
        blocks,
        fallback_text=f"Appointment booked by {event.invitee_name} ({event.invitee_email}) — {start}",
    )


async def notify_pipeline_summary(
    leads_fetched: int,
    leads_verified: int,
    email_enrolled: int,
    linkedin_enrolled: int,
    hubspot_synced: int,
) -> bool:
    """Post an end-of-run summary message."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Pipeline Run Complete",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Leads Fetched:*\n{leads_fetched}"},
                {"type": "mrkdwn", "text": f"*Emails Verified:*\n{leads_verified}"},
                {"type": "mrkdwn", "text": f"*Email Outreach Queued:*\n{email_enrolled}"},
                {"type": "mrkdwn", "text": f"*LinkedIn Outreach Queued:*\n{linkedin_enrolled}"},
                {"type": "mrkdwn", "text": f"*HubSpot Synced:*\n{hubspot_synced}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Run At:*\n{datetime.utcnow().strftime('%b %d, %Y %H:%M UTC')}",
                },
            ],
        },
        {"type": "divider"},
    ]
    return await _post(blocks, fallback_text="Lead pipeline run complete.")
