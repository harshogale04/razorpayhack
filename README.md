# SANDBOX/ — AI-Buyer Transactable Checkout on Razorpay

**Track 01: AI Growth & Agentic Commerce**
*Grow the merchant's revenue, and make them sellable to AI buyers.*

A merchant storefront that is transactable end-to-end by an external AI agent — via a direct API, or by browsing and clicking through a rendered webpage — with every money action **explainable, bounded, and gated** behind a single, non-negotiable safety layer.

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
- [Testing](#testing)
- [Demo script for judges](#demo-script-for-judges)
- [Protocol notes: ACP, UAP, x402](#protocol-notes-acp-uap-x402)
- [License](#license)

---

## Why this exists

Every major player in payments is working on the same problem in 2026: how do you let an AI agent transact on a merchant's behalf, safely? NPCI's Unified Agent Protocol (UAP) for UPI, OpenAI/Stripe's Agentic Commerce Protocol (ACP), Google's AP2, and Coinbase's x402 are all live, competing answers to that question. Razorpay already has in-app agent pilots running.

The hard part was never *letting* an agent buy something — that's an endpoint and a payload. The hard part is **trusting it**. This project is our answer: a real storefront, a real Razorpay test-mode payment pipeline, and a safety layer that keeps AI reasoning and money-moving decisions strictly separate.

## What's actually built

1. **Agent-readable catalog** — `/ai-catalog.json`, structured fields only (`product_id`, SKU, weight, stock, price), no marketing copy
2. **Protocol adoption** — `/purchase-intent` accepts an ACP-shaped purchase-intent payload
3. **End-to-end demo path** — a simulated external AI agent hits the catalog, decides what to buy, and completes a real purchase — via a direct API call, or by browsing and clicking through a rendered storefront, with zero shortcuts either way

On top of the required scope, this build includes a **visual browsing agent**: a real, visible browser (via Playwright) that screenshots the actual storefront, reasons about what's on screen using an LLM's vision model, and clicks real buttons — add to cart, view cart, proceed to checkout, pay — the same way a person would. Nothing here calls an internal function directly; every action, human or agent, goes through the same public HTTP surface a genuinely external system would use.

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
          (the one path to Razorpay)
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
  Stock check   Spending envelope   Razorpay client
  (catalog.py)  (safety.py — pure    (mock mode today,
                 code, no LLM)        live test-mode when
                      │               keys are added)
                      ▼
              app/audit.py (SQLite)
                      │
                      ▼
         Live dashboard (polls /audit-log every 2s)
```

There is exactly one function, `process_order()`, permitted to reach Razorpay, and exactly one place the spending gate lives, regardless of which entry point a request came through.

## The safety layer (the part that matters most)

The track's evaluation bar is: *every money action must be explainable, bounded, and gated.* Concretely:

- **Bounded** — `app/safety.py` hardcodes a spending envelope (default ₹5,000) as a plain Python function. No LLM is involved in this decision. It is a structural, code-level check, not something a model is trusted to judge in the moment.
- **Gated** — Any transaction over the limit halts immediately and is logged as `pending_approval`. It never auto-executes. There is no retry-until-it-fits logic and no partial execution — it stops.
- **Explainable** — Every state transition (intent received → stock checked → envelope checked → Razorpay order created → payment captured, failed, or halted) is written to a SQLite audit log with a human-readable reason, queryable live via `/audit-log` and rendered on a real-time dashboard at `/dashboard`.
- **Graceful failure handling** — Two failure modes are explicitly caught: a simulated network timeout and a simulated card decline (`insufficient_funds`). Both are logged with full context and **halt rather than retry** — blindly retrying a failed payment is how a merchant ends up double-charging a customer.

## Project structure

```
ai-buyer-checkout/
├── app/
│   ├── main.py              # FastAPI app, mounts dashboard + storefront
│   ├── order_processing.py  # The shared core — the one path to Razorpay
│   ├── intent.py            # /purchase-intent — ACP-style single-item API
│   ├── checkout.py          # /checkout — multi-item cart, used by the storefront
│   ├── catalog.py           # Agent-readable product catalog (seed data)
│   ├── safety.py            # The spending envelope gate — pure code, no LLM
│   ├── audit.py             # SQLite audit trail
│   ├── razorpay_client.py   # Razorpay wrapper — mock mode + real test-mode
│   └── models.py            # Pydantic request schemas
├── storefront/
│   └── index.html            # Rendered shop: catalog, cart, payment sheet
├── dashboard/
│   └── index.html            # Live-polling audit trail viewer
├── tests/
│   └── test_safety.py        # Spending envelope tests — no server or credentials needed
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

## Running it

**1. Run the tests** (confirms the safety gate works — no server or credentials needed):
```bash
python -m pytest tests/ -v
```

**2. Start the server** (leave this running in its own terminal):
```bash
uvicorn app.main:app --reload --port 8000
```

**3. Open two browser tabs:**
- `http://localhost:8000/dashboard` — the live audit trail
- `http://localhost:8000/storefront/` — the shop itself

**4. In a separate terminal (virtual environment activated), run a buyer agent:**
```bash
python buyer_agent.py       # API-direct, fast
python browsing_agent.py    # visual browsing, real browser
```

Every new terminal needs the virtual environment activated independently — `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (macOS/Linux) — before running any Python command in it.

## The two buyer agents

Both simulate an *external* AI agent. Neither imports internal application code directly — both communicate over plain HTTP, exactly as a genuine third party would.

### `buyer_agent.py` — API-direct
Fetches the catalog, asks the LLM to pick a sensible set of items within a budget with brief reasoning per item, then submits each as a separate `/purchase-intent` call. Fast and simple — a good sanity check that the end-to-end pipeline behaves correctly.

### `browsing_agent.py` — visual browsing
Opens a real, visible Chromium window via Playwright and loads the storefront. On each step it: takes a screenshot, sends it to the LLM's vision model along with a list of exactly which elements are currently clickable (grounded via `data-agent-action` attributes on every interactive button), receives a decision naming one clickable element, then executes a real mouse click at that element's on-screen position — animated via an injected cursor so the decision is visually legible during a demo or recording. It progresses through add to cart, view cart, proceed to checkout, and pay now — the same sequence a human shopper would follow.

## API reference

### `GET /ai-catalog.json`
Agent-readable catalog. No marketing copy, no images — only what a machine needs to decide.
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
  "payment_credential": "txn_8f21a6c93d",
  "simulate_failure": null
}
```

### `POST /checkout`
Multi-item cart checkout, used by the storefront's payment sheet.
```json
{
  "items": [{ "product_id": "sku-002", "quantity": 2 }, { "product_id": "sku-003", "quantity": 1 }],
  "buyer_agent_id": "storefront-browser",
  "payment_credential": "txn_4b17e2d8a0",
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

## Testing

```bash
python -m pytest tests/ -v
```

Exercises the spending envelope in isolation — under limit, at limit, over limit, zero, and negative amounts — with no server, no Razorpay, and no LLM required. This is the one component of the system that must be provably correct on its own, since it is the entire "bounded" guarantee.

## Demo script for judges

1. Open the dashboard and the storefront side by side.
2. Run `browsing_agent.py` — the LLM is reasoning over real screenshots and clicking real buttons, not calling an API under the hood. Watch it add items, check out, and pay; watch the matching entries land on the dashboard in real time.
3. Re-run with the agent's target budget pushed above the envelope — show the halt happen live, no Razorpay call made, reason logged in plain language.
4. Re-run with a simulated decline — show the failure caught, logged with full context, and **not retried**.
5. Close with: *"Every money action here passes through one code-level gate before it touches Razorpay — not a model's discretion. Anything within the envelope executes and is logged. Anything outside it, or anything that fails, halts and is logged instead of being silently retried. The dashboard you're watching is that log, live."*

## Protocol notes: ACP, UAP, x402

- **ACP** (Agentic Commerce Protocol, OpenAI/Stripe) — this build's `/purchase-intent` payload follows ACP's interaction shape: a structured intent with product ID, quantity, buyer agent ID, and payment credential.
- **UAP** (NPCI's proposed UPI-agent-authorization framework) — noted as a forward-looking design consideration only. UAP is not yet launched or RBI-approved, so this build is designed with UAP-style flows in mind conceptually, not integrated with it.
- **x402** — a crypto/stablecoin-rail micropayment protocol, largely out of scope here since this build is UPI/Razorpay-centric and settles in INR rather than a stablecoin rail. Noted explicitly as a considered tradeoff rather than an oversight.

## License

This project is released under the MIT License. See `LICENSE` for details.
