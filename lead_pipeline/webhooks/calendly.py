"""
Calendly invitee.created webhook handler.

When a lead books a meeting, this module:
  1. Parses the booking into a BookingEvent
  2. Posts a real-time Slack alert
  3. Updates the HubSpot contact stage to BOOKED
  4. Attaches a note with meeting details to the contact
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..crm_sync import add_note, mark_lead_stage, upsert_contact
from ..models import BookingEvent, Lead, LeadSource, EmailStatus
from ..notifications.slack import notify_booking

logger = logging.getLogger(__name__)


def _parse_booking_event(payload: dict[str, Any]) -> BookingEvent | None:
    """Extract a BookingEvent from a Calendly invitee.created payload."""
    try:
        invitee = payload["payload"]["invitee"]
        scheduled_event = payload["payload"]["event"]

        return BookingEvent(
            event_id=scheduled_event.get("uuid", ""),
            event_name=scheduled_event.get("name", "Discovery Call"),
            invitee_name=invitee.get("name", ""),
            invitee_email=invitee.get("email", ""),
            start_time=datetime.fromisoformat(
                scheduled_event["start_time"].replace("Z", "+00:00")
            ),
            end_time=datetime.fromisoformat(
                scheduled_event["end_time"].replace("Z", "+00:00")
            ),
            meeting_url=scheduled_event.get("location", {}).get("join_url"),
            cancel_url=invitee.get("cancel_url"),
            reschedule_url=invitee.get("reschedule_url"),
            utm_source=invitee.get("tracking", {}).get("utm_source"),
        )
    except (KeyError, ValueError) as exc:
        logger.error("Failed to parse Calendly payload: %s", exc)
        return None


async def handle_calendly_event(payload: dict[str, Any]) -> None:
    """Top-level handler — called from the FastAPI route."""
    booking = _parse_booking_event(payload)
    if booking is None:
        return

    logger.info(
        "Calendly booking: %s <%s> scheduled %s",
        booking.invitee_name,
        booking.invitee_email,
        booking.start_time.isoformat(),
    )

    # 1. Fire Slack notification immediately
    await notify_booking(booking)

    # 2. Upsert the lead into HubSpot (creates if they don't exist)
    stub_lead = Lead(
        first_name=booking.invitee_name.split()[0] if booking.invitee_name else "",
        last_name=" ".join(booking.invitee_name.split()[1:]) if booking.invitee_name else "",
        full_name=booking.invitee_name,
        email=booking.invitee_email,  # type: ignore[arg-type]
        title="Prospect",
        source=LeadSource.manual,
        email_status=EmailStatus.valid,
    )
    contact_id = await upsert_contact(stub_lead)

    if contact_id:
        # 3. Update lead stage
        await mark_lead_stage(contact_id, "BOOKED")

        # 4. Attach note
        start_str = booking.start_time.strftime("%A, %b %d at %I:%M %p UTC")
        note = (
            f"Appointment booked via Calendly.\n"
            f"Meeting: {booking.event_name}\n"
            f"When: {start_str}\n"
            f"Cancel URL: {booking.cancel_url or 'N/A'}\n"
            f"Reschedule URL: {booking.reschedule_url or 'N/A'}"
        )
        await add_note(contact_id, note)
