"""
Central configuration — all secrets loaded from environment variables.
Copy .env.example to .env and fill in your values before running.
"""
from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Apollo.io ─────────────────────────────────────────────────────────────
    apollo_api_key: str = Field(..., description="Apollo.io API key")
    apollo_page_size: int = Field(25, ge=1, le=100)
    apollo_max_pages: int = Field(20, ge=1, le=100)  # 500 leads max per run

    # ── ZeroBounce (email verification) ───────────────────────────────────────
    zerobounce_api_key: str = Field(..., description="ZeroBounce API key")

    # ── HubSpot CRM ───────────────────────────────────────────────────────────
    hubspot_access_token: str = Field(..., description="HubSpot private app token")

    # ── Instantly.ai (cold email) ─────────────────────────────────────────────
    instantly_api_key: str = Field(..., description="Instantly.ai API key")
    instantly_campaign_id: str = Field(..., description="Active campaign ID in Instantly")

    # ── Expandi.io (LinkedIn outreach) ────────────────────────────────────────
    expandi_api_key: str = Field(..., description="Expandi.io API key")
    expandi_campaign_id: str = Field(..., description="Active campaign ID in Expandi")

    # ── Calendly ──────────────────────────────────────────────────────────────
    calendly_webhook_signing_key: str = Field(
        ..., description="Calendly webhook signing secret"
    )

    # ── Slack ─────────────────────────────────────────────────────────────────
    slack_webhook_url: str = Field(..., description="Slack incoming webhook URL")
    slack_channel: str = Field("#insurance-leads", description="Target Slack channel")

    # ── Webhook server ────────────────────────────────────────────────────────
    webhook_host: str = Field("0.0.0.0")
    webhook_port: int = Field(8000, ge=1024, le=65535)
    webhook_secret: str = Field(..., description="Shared secret for Instantly webhooks")

    # ── Pipeline behaviour ────────────────────────────────────────────────────
    target_titles: list[str] = Field(
        default=[
            "CPA",
            "Certified Public Accountant",
            "Financial Planner",
            "CFP",
            "Financial Advisor",
            "Tax Advisor",
            "Accountant",
        ]
    )
    target_state: str = Field("Utah")
    dry_run: bool = Field(False, description="Log actions without calling outreach APIs")

    @field_validator("slack_webhook_url")
    @classmethod
    def _validate_slack_url(cls, v: str) -> str:
        if not v.startswith("https://hooks.slack.com/"):
            raise ValueError("slack_webhook_url must be a hooks.slack.com URL")
        return v


# Module-level singleton — import this everywhere
settings = Settings()  # type: ignore[call-arg]
