"""Shared Pydantic data models for the entire pipeline."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, HttpUrl


class LeadSource(str, Enum):
    apollo = "apollo"
    manual = "manual"


class EmailStatus(str, Enum):
    valid = "valid"
    invalid = "invalid"
    catch_all = "catch_all"
    unknown = "unknown"
    do_not_mail = "do_not_mail"


class OutreachChannel(str, Enum):
    email = "email"
    linkedin = "linkedin"


class OutreachStatus(str, Enum):
    queued = "queued"
    sent = "sent"
    replied = "replied"
    bounced = "bounced"
    opted_out = "opted_out"


class Lead(BaseModel):
    """Canonical lead record used throughout the pipeline."""

    # Identity
    first_name: str
    last_name: str
    full_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

    # Professional
    title: str
    company: Optional[str] = None
    company_website: Optional[str] = None

    # Location
    city: Optional[str] = None
    state: Optional[str] = None

    # Social
    linkedin_url: Optional[HttpUrl] = None

    # Pipeline metadata
    source: LeadSource = LeadSource.apollo
    email_status: EmailStatus = EmailStatus.unknown
    apollo_id: Optional[str] = None
    hubspot_contact_id: Optional[str] = None
    created_at: datetime = datetime.utcnow()  # noqa: B008  (intentional default)


class OutreachRecord(BaseModel):
    lead_email: str
    channel: OutreachChannel
    status: OutreachStatus
    campaign_id: str
    sent_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    notes: Optional[str] = None


class BookingEvent(BaseModel):
    """Parsed Calendly invitee.created webhook payload."""

    event_id: str
    event_name: str
    invitee_name: str
    invitee_email: str
    start_time: datetime
    end_time: datetime
    meeting_url: Optional[str] = None
    cancel_url: Optional[str] = None
    reschedule_url: Optional[str] = None
    utm_source: Optional[str] = None
    received_at: datetime = datetime.utcnow()  # noqa: B008


class EmailReplyEvent(BaseModel):
    """Parsed Instantly.ai reply webhook payload."""

    lead_email: str
    lead_name: Optional[str] = None
    campaign_id: str
    campaign_name: Optional[str] = None
    reply_text: str
    replied_at: datetime
    thread_id: Optional[str] = None
    received_at: datetime = datetime.utcnow()  # noqa: B008
