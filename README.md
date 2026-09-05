# SANDBOX/ — AI-Buyer Transactable Checkout on Razorpay

**Track 01: AI Growth & Agentic Commerce**
*Grow the merchant's revenue, and make them sellable to AI buyers.*

A merchant storefront that's transactable end-to-end by an external AI agent — via a direct API, or by genuinely browsing and clicking through a rendered webpage — with every money action **explainable, bounded, and gated** behind a single, non-negotiable safety layer.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [What's actually built](#whats-actually-built)
- [Architecture](#architecture)
- [The safety layer](#the-safety-layer-the-part-that-matters-most)
- [Project structure](#project-structure)
- [Setup](#setup)
- [Running it](#running-it)
- [The two buyer agents](#the-two-buyer-agents)
- [API reference](#api-reference)
- [Environment variables](#environment-variables)
- [Testing](#testing)
- [Demo script for judges](#demo-script-for-judges)
- [Protocol notes: ACP, UAP, x402](#protocol-notes-acp-uap-x402)
- [Known limitations & roadmap](#known-limitations--roadmap)
- [License](#license)

---

## Why this exists

Every major player in payments is racing to solve the same problem in 2026: how do you let an AI agent transact on a merchant's behalf, safely? NPCI's Unified Agent Protocol (UAP) for UPI, OpenAI/Stripe's Agentic Commerce Protocol (ACP), Google's AP2, and Coinbase's x402 are all live, competing answers to that question. Razorpay already has in-app agent pilots running.

The hard part was never *letting* an agent buy something — that's just an endpoint and a payload. The hard part is **trusting it**. This project is our answer: a real storefront, a real Razorpay test-mode payment pipeline, and a safety layer that keeps AI reasoning and money-moving decisions strictly separate.

## What's actually built

This is **Direction B** from the track brief — AI-Buyer Transactable Checkout — covering all three of its required pieces:

1. **Agent-readable catalog** — `/ai-catalog.json`, structured fields only (`product_id`, SKU, weight, stock, price), no marketing copy
2. **Protocol adoption** — `/purchase-intent` accepts an ACP-shaped purchase-intent payload
3. **End-to-end demo path** — a simulated external AI agent hits the catalog, decides what to buy, and completes a real purchase — via a direct API call *or* by genuinely browsing and clicking through a rendered storefront, with zero shortcuts either way

On top of the required scope, this build adds a **visual browsing agent**: a real, visible browser (via Playwright) that screenshots the actual storefront, reasons about what's on screen using Gemini's vision model, and clicks real buttons — add to cart, view cart, proceed to checkout, pay — the same way a person would. Nothing here calls an internal function directly; every action, human or agent, goes through the same public HTTP surface a genuinely external system would use.

## Architecture

There are three ways into this system — a raw API for agents that want to transact directly, a rendered storefront for agents (or humans) that browse visually, and the demo scripts that drive both — but **all three collapse into one single path** before any money moves:

```
 ACP-style API           Rendered storefront          Demo scripts
 (/purchase-intent)      (click-through checkout)      (buyer_agent.py,
        │                        │                      browsing_agent.py)
        │                        │                            │
        └────────────┬───────────┴────────────────────────────┘
                      ▼
          app/order_processing.py
          (the ONE path to Razorpay)
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
  Stock check   Spending envelope   Razorpay client
  (catalog.py)  (safety.py — pure   (mock mode today,
                 code, no LLM)       live test-mode when
                      │              keys are added)
                      ▼
              app/audit.py (SQLite)
                      │
                      ▼
         Live dashboard (polls /audit-log every 2s)
```

This is deliberate: there is exactly one function, `process_order()`, that is allowed to reach Razorpay, and exactly one place the spending gate lives, no matter which front door a request came through.

## The safety layer (the part that matters most)

The track's evaluation bar is: *every money action must be explainable, bounded, and gated.* Concretely, that means:

- **Bounded** — `app/safety.py` hardcodes a spending envelope (default ₹5,000) as a plain Python function. No LLM is involved in this decision, ever. This is a structural code-level check, not something a model is trusted to judge in the moment.
- **Gated** — Any transaction over the limit halts immediately and is logged as `pending_approval`. It never auto-executes. There is no retry-until-it-fits logic, no partial execution — it stops, full stop.
- **Explainable** — Every state transition (intent received → stock checked → envelope checked → Razorpay order created → payment captured/failed/halted) is written to a SQLite audit log with a human-readable reason, queryable live via `/audit-log` and rendered on a real-time dashboard at `/dashboard`.
- **Graceful failure handling** — Two failure modes are explicitly caught: a simulated network timeout and a simulated card decline (`insufficient_funds`). Both are logged with full context and **halt rather than retry** — blindly retrying a failed payment is how you accidentally double-charge someone.

## Project structure

```
ai-buyer-checkout/
├── app/
│   ├── main.py              # FastAPI app, mounts dashboard + storefront
│   ├── order_processing.py  # THE shared core — the one path to Razorpay
│   ├── intent.py            # /purchase-intent — ACP-style single-item API
│   ├── checkout.py          # /checkout — multi-item cart, used by the storefront
│   ├── catalog.py           # Agent-readable product catalog (seed data)
│   ├── safety.py            # The spending envelope gate — pure code, no LLM
│   ├── audit.py             # SQLite audit trail
│   ├── razorpay_client.py   # Razorpay wrapper — mock mode + real test-mode
│   └── models.py             # Pydantic request schemas
├── storefront/
│   └── index.html            # Rendered shop: catalog, cart, payment sheet
├── dashboard/
│   └── index.html            # Live-polling audit trail viewer
├── tests/
│   └── test_safety.py        # Spending envelope tests — no server/creds needed
├── buyer_agent.py            # Simple demo: AI agent buys via the raw API
├── browsing_agent.py         # Visual demo: AI agent buys via a real browser
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

```bash
git clone <this-repo>
cd ai-buyer-checkout
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium   # only needed for browsing_agent.py

cp .env.example .env
```

Open `.env` and fill in at minimum a `GEMINI_API_KEY` if you want to run either demo agent (get one free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)). Everything else works out of the box in mock mode — **no Razorpay credentials are required to build, run, or demo this project.**

## Running it

**1. Run the tests** (confirms the safety gate works, no server or credentials needed):
```bash
python -m pytest tests/ -v
```

**2. Start the server** (leave this running in its own terminal):
```bash
uvicorn app.main:app --reload --port 8000
```

**3. Open two browser tabs to watch:**
- `http://localhost:8000/dashboard` — the live audit trail
- `http://localhost:8000/storefront/` — the shop itself

**4. In a separate terminal (venv activated), run a buyer agent:**
```bash
python buyer_agent.py       # fast, API-only, ~1 Gemini call
python browsing_agent.py    # visual, real browser, ~5-9 Gemini calls
```

Every new terminal needs the virtual environment activated independently — `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (macOS/Linux) — before running any Python command in it.

## The two buyer agents

Both simulate an *external* AI agent — neither imports internal application code directly, both talk over plain HTTP exactly like a real third party would.

### `buyer_agent.py` — API-direct
Fetches the catalog, asks Gemini (text-only) to pick 2–3 sensible items within a budget with one-line reasoning per item, then submits each as a separate `/purchase-intent` call. Fast, cheap on API quota, good for sanity-checking the pipeline.

### `browsing_agent.py` — visual browsing
Opens a real, visible Chromium window via Playwright and loads the storefront. On each step it: takes a screenshot → sends it to Gemini's vision model along with a list of exactly which elements are currently clickable (grounded via `data-agent-action` attributes on every interactive button) → gets back a decision naming one clickable element → executes a real mouse click at that element's actual on-screen position, animated via an injected on-page cursor so the decision is visually legible in a demo or recording. Loops through add-to-cart → view cart → proceed to checkout → pay now, the same sequence a human would follow.

Both scripts share the same `.env` config:

```bash
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
BUYER_BUDGET_PAISE=400000          # agent's target spend, in paise (₹4000 default)
BROWSING_MAX_STEPS=9               # click budget before the browsing agent gives up
BROWSING_SIMULATE_FAILURE=         # "decline" to force a failed payment through the storefront
```

To watch the spending envelope halt a transaction live, push the agent's budget above your configured limit:
```bash
# Windows PowerShell
$env:BUYER_BUDGET_PAISE="700000"; python browsing_agent.py
```

## API reference

### `GET /ai-catalog.json`
Agent-readable catalog. No marketing copy, no images — just what a machine needs to decide.
```json
{
  "products": [
    { "product_id": "sku-002", "sku": "MUG-CERAMIC-350ML", "unit_weight_g": 320, "stock": 15, "price_paise": 34900 }
  ]
}
```

### `POST /purchase-intent`
ACP-style single-item purchase intent, for agents transacting directly against the API.
```json
{
  "intent": "purchase",
  "product_id": "sku-002",
  "quantity": 2,
  "buyer_agent_id": "agent-demo-1",
  "payment_credential": "tok_mock_abc",
  "simulate_failure": null
}
```

### `POST /checkout`
Multi-item cart checkout, used by the storefront's payment sheet.
```json
{
  "items": [{ "product_id": "sku-002", "quantity": 2 }, { "product_id": "sku-003", "quantity": 1 }],
  "buyer_agent_id": "storefront-browser",
  "payment_credential": "tok_mock_storefront",
  "simulate_failure": null
}
```

**Both endpoints return one of:**
| Status | Meaning |
|---|---|
| `200` | Payment captured — includes `order_ref`, `razorpay_order_id`, `payment_id`, `amount_paise` |
| `202` | Halted for human approval — over the spending envelope, nothing executed |
| `402` | Payment declined (simulated or real) |
| `404` | Unknown `product_id` |
| `409` | Insufficient stock |
| `504` | Payment timed out (simulated) |

### `GET /audit-log?limit=50`
Recent audit trail events, most recent first. Polled by the dashboard every 2 seconds.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | *(empty)* | Real Razorpay test-mode credentials |
| `MOCK_MODE` | `true` | `true` simulates Razorpay responses; `false` calls the real test-mode API |
| `SPENDING_LIMIT_PAISE` | `500000` | The hardcoded envelope — ₹5,000 |
| `APPROVAL_WEBHOOK_URL` | *(empty)* | Where halted-transaction notifications would post (currently logs only) |
| `GEMINI_API_KEY` | *(empty)* | Required by both demo agents |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Swap if this model is unavailable on your tier |
| `BUYER_BUDGET_PAISE` | `400000` | Demo agent's target spend, ₹4,000 |
| `BROWSING_MAX_STEPS` | `9` | Click budget for the browsing agent |
| `BROWSING_SIMULATE_FAILURE` | *(empty)* | `decline` or `timeout` to force a failure through the storefront |
| `BROWSING_CURSOR_MOVE_MS` | `280` | Cursor animation speed (browsing agent) |
| `SERVER_URL` | `http://localhost:8000` | Used by both demo scripts |

## Testing

```bash
python -m pytest tests/ -v
```

Exercises the spending envelope in isolation — under limit, at limit, over limit, zero, negative — with no server, no Razorpay, no Gemini required. This is the one piece of the system that must be provably correct on its own, since it's the entire "bounded" guarantee.

## Demo script for judges

1. Open the dashboard and the storefront side by side.
2. Run `browsing_agent.py` — narrate that Gemini is looking at real screenshots and clicking real buttons, not calling an API under the hood. Watch it add items, check out, and pay live; watch the matching rows land on the dashboard in real time.
3. Re-run with `BUYER_BUDGET_PAISE` pushed above the envelope — show the halt happen live, no Razorpay call made, reason logged in plain language.
4. Re-run with `BROWSING_SIMULATE_FAILURE=decline` — show the failure caught, logged with full context, and **not retried**.
5. Close with: *"Every money action here passes through one code-level gate before it touches Razorpay — not a model's discretion. Anything within the envelope executes and is logged. Anything outside it, or anything that fails, halts and is logged instead of silently retrying. The dashboard you're watching is that log, live."*

## Protocol notes: ACP, UAP, x402

- **ACP** (Agentic Commerce Protocol, OpenAI/Stripe) — this build's `/purchase-intent` payload follows ACP's interaction shape: a structured intent with product ID, quantity, buyer agent ID, and payment credential.
- **UAP** (NPCI's proposed UPI-agent-authorization framework) — noted as a forward-looking design consideration only. UAP is not yet launched or RBI-approved, so this build is *designed for* UAP-style flows conceptually, not integrated with it.
- **x402** — a crypto/stablecoin-rail micropayment protocol, largely out of scope here since this build is UPI/Razorpay-centric and settles in INR, not a stablecoin rail. Noted explicitly rather than ignored, as a real tradeoff worth acknowledging.

## Known limitations & roadmap

- Catalog is in-memory seed data — swap for a real product DB for production use
- Human-approval halts currently log only; `APPROVAL_WEBHOOK_URL` is wired but not posting anywhere real yet
- Free-tier Gemini API is rate-limited to 20 requests/day — fine for occasional demos, not for heavy iteration; enable billing on your Google AI Studio project before relying on this for a live audience
- `google-generativeai` is Google's deprecated SDK (superseded by `google-genai`) — still functional as of this build, worth migrating post-hackathon
- No real webhook delivery, no persistent product DB, no multi-merchant support — intentionally out of scope for a two-week build

## License

MIT — see `LICENSE` for details, or add one if not yet present.
