"""
FastAPI webhook server.

Exposes two inbound webhook endpoints:
  POST /webhooks/calendly    — Calendly invitee.created events
  POST /webhooks/email-reply — Instantly.ai reply events

Run with:
  uvicorn lead_pipeline.webhooks.server:app --host 0.0.0.0 --port 8000

In production, put this behind nginx/Caddy + TLS, then configure the
public URL as the webhook destination in Calendly and Instantly dashboards.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ..config import settings
from .calendly import handle_calendly_event
from .email_reply import handle_email_reply_event

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    logger.info(
        "Webhook server started — listening on %s:%d",
        settings.webhook_host,
        settings.webhook_port,
    )
    yield
    logger.info("Webhook server shutting down.")


app = FastAPI(
    title="Insurance Lead Pipeline Webhooks",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",  # Disable in production: docs_url=None
)


# ── Signature verification helpers ────────────────────────────────────────────


def _verify_calendly_signature(
    raw_body: bytes,
    signature_header: str | None,
    signing_key: str,
) -> bool:
    """
    Calendly uses HMAC-SHA256 for webhook signature verification.
    Header format: t=<timestamp>,v1=<hex_signature>
    """
    if not signature_header:
        return False
    try:
        parts = dict(part.split("=", 1) for part in signature_header.split(","))
        timestamp = parts.get("t", "")
        v1_sig = parts.get("v1", "")
        signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
        expected = hmac.new(
            signing_key.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, v1_sig)
    except Exception:
        return False


def _verify_instantly_signature(
    raw_body: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Instantly.ai uses a simple HMAC-SHA256 header: X-Webhook-Signature."""
    if not signature_header:
        return False
    expected = hmac.new(
        secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/webhooks/calendly", status_code=status.HTTP_200_OK)
async def calendly_webhook(
    request: Request,
    calendly_webhook_signature: str | None = Header(None, alias="Calendly-Webhook-Signature"),
) -> JSONResponse:
    raw_body = await request.body()

    if not _verify_calendly_signature(
        raw_body,
        calendly_webhook_signature,
        settings.calendly_webhook_signing_key,
    ):
        logger.warning("Calendly webhook: invalid signature — rejecting.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    payload: dict[str, Any] = await request.json()
    event_type: str = payload.get("event", "")

    if event_type == "invitee.created":
        await handle_calendly_event(payload)
    else:
        logger.debug("Calendly webhook: ignoring event type '%s'", event_type)

    return JSONResponse({"received": True})


@app.post("/webhooks/email-reply", status_code=status.HTTP_200_OK)
async def email_reply_webhook(
    request: Request,
    x_webhook_signature: str | None = Header(None, alias="X-Webhook-Signature"),
) -> JSONResponse:
    raw_body = await request.body()

    if not _verify_instantly_signature(
        raw_body,
        x_webhook_signature,
        settings.webhook_secret,
    ):
        logger.warning("Instantly webhook: invalid signature — rejecting.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    payload: dict[str, Any] = await request.json()
    await handle_email_reply_event(payload)

    return JSONResponse({"received": True})
