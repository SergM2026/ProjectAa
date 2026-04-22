# Insurance Lead Generation Pipeline
**Target**: CPAs & Financial Planners in Utah  
**Goal**: Automated multi-channel outreach → appointments → Slack alerts

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Lead Sourcing | **Apollo.io** ($49+/mo) | Largest B2B database; API supports job-title + state filters |
| Email Verification | **ZeroBounce** (pay-per-use) | Industry-standard accuracy; batch API; prevents bounces |
| Cold Email Outreach | **Instantly.ai** ($37+/mo) | Built-in inbox warm-up, rotation, reply detection, webhooks |
| LinkedIn Outreach | **Expandi.io** ($99/mo) | Cloud-based (no browser extension); enforces daily limits |
| CRM | **HubSpot** (free tier) | Webhook-friendly; free contacts, notes, deal pipeline |
| Scheduling | **Calendly** ($8/mo) | Industry-standard; embeds in email; webhook on booking |
| Orchestration | **n8n** (self-hosted free) | Visual workflows; connects all tools; cron scheduling |
| Webhook Server | **FastAPI + uvicorn** | Async Python; receives Calendly + Instantly events |
| Notifications | **Slack Incoming Webhooks** | Free; real-time; rich Block Kit formatting |
| Language | **Python 3.11+** | Async-first; best library ecosystem for this stack |

---

## Architecture Blueprint

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SCHEDULED PIPELINE RUN                          │
│                     (n8n cron: Mon/Wed/Fri 7am)                         │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   1. Apollo.io API        │
                    │   Filter: CPA + FP        │
                    │   Location: Utah          │
                    │   Output: ~500 leads/run  │
                    └─────────────┬─────────────┘
                                  │  List[Lead]
                    ┌─────────────▼─────────────┐
                    │   2. ZeroBounce API       │
                    │   Batch verify emails     │
                    │   Drop: invalid/spam      │
                    └─────────────┬─────────────┘
                                  │  List[Lead] (valid emails only)
          ┌───────────────────────┼────────────────────────┐
          │                       │                        │
┌─────────▼─────────┐  ┌──────────▼──────────┐  ┌────────▼────────────┐
│  3. HubSpot CRM   │  │  4. Instantly.ai    │  │  5. Expandi.io      │
│  Upsert contact   │  │  Enroll in email    │  │  Enroll in LinkedIn │
│  Set stage: NEW   │  │  sequence campaign  │  │  connection campaign │
└───────────────────┘  └─────────────────────┘  └─────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   6. Slack Summary        │
                    │   #insurance-leads        │
                    │   Leads/enrolled/synced   │
                    └───────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────┐
│                        INBOUND EVENTS (Real-time)                       │
└─────────────────────────────────────────────────────────────────────────┘

   Instantly.ai                                        Calendly
   (lead replies)                                     (lead books)
        │                                                   │
        │  POST /webhooks/email-reply                       │  POST /webhooks/calendly
        │  X-Webhook-Signature: <hmac>                      │  Calendly-Webhook-Signature: <hmac>
        │                                                   │
        └──────────────┬────────────────────────────────────┘
                       │
             ┌─────────▼──────────┐
             │  FastAPI Server    │
             │  (lead_pipeline/   │
             │   webhooks/)       │
             └────────┬───────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
┌───────▼──────┐  ┌───▼───┐  ┌─────▼──────────────┐
│ Slack Alert  │  │Pause  │  │ HubSpot: update     │
│ #insurance-  │  │lead in│  │ stage (REPLIED /    │
│ leads        │  │Instant│  │ BOOKED) + note      │
└──────────────┘  └───────┘  └─────────────────────┘
```

---

## Step-by-Step Implementation Plan

### Phase 1 — API Keys & Accounts (Day 1, ~2 hours)

Get credentials for each service in this order:

1. **Apollo.io**
   - Sign up at apollo.io → Settings → Integrations → API
   - Get your API key
   - _Required plan_: Basic ($49/mo) or higher for API access

2. **ZeroBounce**
   - Sign up at zerobounce.net → Members → API Key
   - Purchase a credit pack (1,000 credits ≈ $16; 10,000 ≈ $80)

3. **HubSpot**
   - Create a free account → Settings → Integrations → Private Apps
   - Create a Private App with scopes:
     - `crm.objects.contacts.read`
     - `crm.objects.contacts.write`
     - `crm.objects.notes.write`
   - Copy the generated token

4. **Instantly.ai**
   - Sign up at instantly.ai → Settings → Integrations → API
   - Create an email campaign: "Utah CPA/FP Outreach"
   - Upload 3–5 warmed-up sending mailboxes to the campaign
   - Copy the campaign ID from the URL
   - Set up your email sequence (see Email Templates section below)

5. **Expandi.io**
   - Sign up at expandi.io → connect your LinkedIn account
   - Create a campaign: "Utah CPA/FP LinkedIn Outreach"
   - Set connection limit to **20/day** in campaign settings
   - Enable "Work hours only" scheduling
   - Copy the API key and campaign ID

6. **Calendly**
   - Create an event type: "15-min Insurance Discovery Call"
   - Settings → Integrations → Webhooks → Create Webhook
   - Set destination URL to your server: `https://yourdomain.com/webhooks/calendly`
   - Subscribe to `invitee.created` event
   - Copy the signing key

7. **Slack**
   - Go to api.slack.com/apps → Create App → Incoming Webhooks
   - Activate and add to `#insurance-leads` channel
   - Copy the webhook URL

### Phase 2 — Local Setup (Day 1–2, ~1 hour)

```bash
# Clone and set up
cd ProjectAa
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Verify all connections
python scripts/verify_setup.py
```

### Phase 3 — Smoke Test (Day 2, ~30 min)

```bash
# Dry run — fetches leads but writes nothing to APIs
python scripts/run_pipeline.py --dry-run --max-pages 1

# Check the output looks correct, then run live with 1 page (~25 leads)
python scripts/run_pipeline.py --max-pages 1
```

### Phase 4 — Deploy Webhook Server (Day 2–3)

**Option A: VPS (DigitalOcean/Linode, ~$6/mo)**
```bash
# On your server
git clone <repo> && cd ProjectAa
cp .env.example .env && nano .env

pip install -r requirements.txt gunicorn

# Start with gunicorn (production)
gunicorn lead_pipeline.webhooks.server:app \
  -w 2 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000

# Put behind Caddy or nginx for TLS (required for Calendly + Instantly webhooks)
```

**Option B: Railway / Render (free tier, easiest)**
- Connect your GitHub repo
- Set all env vars in the dashboard
- Deploy command: `gunicorn lead_pipeline.webhooks.server:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT`

### Phase 5 — Import n8n Workflows (Day 3)

1. Install n8n: `npx n8n` or use n8n Cloud ($20/mo)
2. Import `n8n_workflows/lead_ingestion.json` → activates the Mon/Wed/Fri cron
3. Import `n8n_workflows/reply_notification.json` → webhook forwarding

### Phase 6 — Go Live (Day 3–4)

1. Update Calendly webhook URL to your deployed server
2. Update Instantly webhook URL to your deployed server
3. Run a full live pipeline: `python scripts/run_pipeline.py`
4. Confirm leads appear in HubSpot, Instantly, and Expandi
5. Confirm Slack receives the summary message

---

## Email Sequence (Instantly.ai)

Set up a 4-step sequence in Instantly with these intervals:

| Email | Delay | Subject | Purpose |
|---|---|---|---|
| #1 | Send immediately | `Quick question about your practice's coverage, {{first_name}}` | Introduce, soft ask |
| #2 | +3 days | `Re: Business insurance for {{title}}s` | Brief follow-up, add value |
| #3 | +5 days | `One thing most {{title}}s overlook` | Value email (E&O / cyber risk angle) |
| #4 | +7 days | `Last note from me, {{first_name}}` | Final breakup email |

**Subject line tips**: Keep under 50 chars. Use `{{first_name}}` and `{{title}}` variables. Avoid spam trigger words (free, guaranteed, click here).

**Body personalization variable**: Use `{{personalization}}` — the pipeline auto-generates this per lead (e.g., *"As a CPA in Salt Lake City, protecting your practice from E&O and cyber liability is mission-critical..."*).

**Calendly CTA**: End every email with:
```
If any of this resonates, here's a link to grab 15 minutes with me:
[Book a call → YOUR_CALENDLY_LINK]
```

---

## LinkedIn Sequence (Expandi)

| Step | Delay | Action | Message |
|---|---|---|---|
| 1 | Immediately | Connection request | `{{connection_note}}` (auto-generated, ≤300 chars) |
| 2 | +2 days after accept | Direct message | Value message (no pitch) |
| 3 | +5 days | Direct message | Soft CTA with Calendly link |

**Connection note template** (configured in pipeline):
> *"Hi {{first_name}}, I work with {{title}}s in Utah on business insurance tailored to your industry. Would love to connect!"*

---

## Compliance & Anti-Spam

### Email Deliverability

| Practice | Implementation |
|---|---|
| **Inbox warm-up** | Instantly.ai has built-in warm-up — enable it for all mailboxes for at least 2 weeks before sending cold email |
| **Sending domain** | Use a subdomain of your main domain (e.g., `outreach.youragency.com`), never your primary domain |
| **SPF + DKIM + DMARC** | Set DNS records for each sending domain before launching (Instantly guides you through this) |
| **Volume limits** | Cap at 30–40 emails/day per mailbox; rotate across 3–5 mailboxes in the campaign |
| **ZeroBounce filtering** | Never send to `invalid` or `do_not_mail` addresses — the pipeline enforces this automatically |
| **Unsubscribe** | Include a one-click unsubscribe link (Instantly adds this automatically via `{{unsubscribe}}`) |
| **CAN-SPAM compliance** | Always include your physical mailing address in the footer |
| **Reply handling** | When a lead replies, the pipeline immediately pauses them in Instantly so no further emails send |

### LinkedIn Safety

| Practice | Implementation |
|---|---|
| **Daily connection limit** | Set Expandi campaign to **max 20 connection requests/day** — LinkedIn's observed safe threshold is ~20–25 |
| **Randomized delays** | Expandi randomizes 2–15 min gaps between actions; enable "Human behavior simulation" in campaign settings |
| **Business hours only** | Enable "Active hours" in Expandi — Mountain Time, weekdays only |
| **Profile completeness** | Ensure your LinkedIn profile is 100% complete with a professional photo before starting |
| **Warm-up period** | For a new LinkedIn account, start at 5 connections/day for week 1, 10 for week 2, then 20 from week 3 |
| **LinkedIn Sales Navigator** | Consider upgrading ($99/mo) — it provides richer search filters and reduces automation detection risk |
| **Account monitoring** | Check your LinkedIn account daily the first two weeks; if you get a login challenge, stop Expandi immediately and answer it |

### Legal

- **CAN-SPAM Act (email)**: Identify yourself, include opt-out mechanism, honor opt-outs within 10 days, include physical address. Instantly handles most of this automatically.
- **TCPA (calls/texts)**: Not applicable here since you're not calling or texting.
- **Utah business contacts**: B2B outreach to professionals is generally permitted under CAN-SPAM; CPAs and financial planners are commercial entities.
- **LinkedIn ToS**: Automated connection requests are technically against ToS. Expandi operates within their tolerance zone by mimicking human behavior and respecting daily limits. Acknowledge the risk; it is widely used in B2B sales.

---

## Project File Map

```
ProjectAa/
├── lead_pipeline/
│   ├── config.py               # All settings loaded from .env
│   ├── models.py               # Pydantic data models (Lead, BookingEvent, etc.)
│   ├── apollo_client.py        # Apollo.io People Search API
│   ├── enrichment.py           # ZeroBounce email verification
│   ├── crm_sync.py             # HubSpot contact upsert + notes
│   ├── pipeline.py             # Main orchestration (steps 1–6)
│   ├── outreach/
│   │   ├── instantly_client.py # Cold email enrollment + pause
│   │   └── expandi_client.py   # LinkedIn campaign enrollment
│   ├── notifications/
│   │   └── slack.py            # Block Kit messages (reply, booking, summary)
│   └── webhooks/
│       ├── server.py           # FastAPI app + signature verification
│       ├── calendly.py         # invitee.created handler
│       └── email_reply.py      # reply_received handler
├── n8n_workflows/
│   ├── lead_ingestion.json     # Cron trigger + pipeline run
│   └── reply_notification.json # Webhook forwarding to Python server
├── scripts/
│   ├── run_pipeline.py         # CLI: run the pipeline
│   ├── run_webhook_server.py   # CLI: start webhook server
│   └── verify_setup.py        # Pre-flight API key checker
├── .env.example                # Copy to .env, fill in keys
├── .gitignore
└── requirements.txt
```

---

## Monthly Cost Estimate

| Tool | Plan | Cost |
|---|---|---|
| Apollo.io | Basic | $49/mo |
| ZeroBounce | Credits | ~$20/mo |
| Instantly.ai | Growth | $37/mo |
| Expandi.io | Business | $99/mo |
| Calendly | Standard | $8/mo |
| HubSpot | Free | $0 |
| n8n | Self-hosted | $0 (or $20/mo cloud) |
| VPS (webhook server) | DigitalOcean | $6/mo |
| **Total** | | **~$219/mo** |

---

## Quick-Start Checklist

- [ ] Get Apollo.io API key
- [ ] Get ZeroBounce API key + purchase credits
- [ ] Create HubSpot private app + copy token
- [ ] Set up Instantly.ai campaign with 3+ warmed inboxes
- [ ] Set up Expandi.io campaign (limit: 20 connections/day)
- [ ] Create Calendly event type for discovery calls
- [ ] Create Slack incoming webhook for `#insurance-leads`
- [ ] Copy `.env.example` → `.env`, fill in all values
- [ ] Run `python scripts/verify_setup.py` → all green
- [ ] Run `python scripts/run_pipeline.py --dry-run` → verify output
- [ ] Deploy webhook server to VPS or Railway
- [ ] Update Calendly + Instantly webhook URLs to deployed server
- [ ] Import n8n workflows and activate
- [ ] Run first live pipeline → confirm leads in HubSpot, Slack summary received
