# AI-buyer transactable checkout (Razorpay test-mode)

Direction B build for the "AI Growth & Agentic Commerce" track: makes a merchant
transactable end-to-end by an external AI buyer agent, with every money action
explainable, bounded, and gated.

## Status

Fully working in `MOCK_MODE=true` today, with no Razorpay credentials required.
Once you have test-mode keys, set `MOCK_MODE=false` in `.env` and every call in
`app/razorpay_client.py` goes to the real Razorpay test API instead — nothing
else in the system changes.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # defaults work out of the box in mock mode
uvicorn app.main:app --reload --port 8000
```

Open the live audit dashboard: http://localhost:8000/dashboard

## Endpoints

- `GET /ai-catalog.json` — agent-readable catalog (product_id, sku, weight, stock, price)
- `POST /purchase-intent` — ACP-style purchase intent payload:
  ```json
  {
    "intent": "purchase",
    "product_id": "sku-002",
    "quantity": 2,
    "buyer_agent_id": "agent-demo-1",
    "payment_credential": "tok_mock_abc"
  }
  ```
- `GET /audit-log` — recent audit trail events (JSON), polled by the dashboard

## The safety layer

- `app/safety.py` — the spending envelope check. Pure function, no LLM
  anywhere in the decision. Default limit ₹5000 (`SPENDING_LIMIT_PAISE=500000`),
  set in `.env`. Anything over the limit is rejected with HTTP 202
  `halted_for_human_approval` and never reaches Razorpay.
- `app/audit.py` — every state change (intent received, envelope check,
  order created, payment captured/failed, halted) is written to SQLite.
  Query live via `/audit-log` or the dashboard.
- `app/razorpay_client.py` — failure handling for network timeout and a
  test-mode card decline. Both are caught, logged with full context, and
  halt rather than retry (to avoid double-charging).

## Demo script (2 minutes)

1. Show the catalog: `curl localhost:8000/ai-catalog.json`
2. Open the dashboard, leave it visible.
3. Fire a normal intent (e.g. sku-002, qty 2) — watch it succeed live in the dashboard.
4. Fire an intent that exceeds ₹5000 (e.g. sku-004, qty 5) — watch it halt at
   `envelope_check: blocked` and `halted_for_approval`, no Razorpay call made.
5. Fire an intent with `"simulate_failure": "decline"` — watch `payment_failed`
   land in the audit trail with the decline reason, and confirm no retry happened.
6. Say the line: *"Every money action here passes through one code-level gate
   before it touches Razorpay — not a model's discretion. Anything within the
   envelope executes and is logged. Anything outside it, or anything that fails,
   halts and is logged with full context instead of silently retrying. The
   dashboard you're watching is that log, live."*

## Roadmap / nice-to-haves (not required for the safety-layer bar)

- Swap catalog seed data for a real product DB
- Real webhook delivery for human-approval halts (currently logs only)
- MCP server variant of the catalog alongside the JSON endpoint
- UAP (NPCI's proposed UPI-agent-authorization framework) is noted as a
  forward-looking design consideration only — not RBI-approved yet, so this
  build targets ACP's payload shape and does not integrate UAP.
- x402 (crypto/stablecoin micropayment rail) is out of scope — this build is
  UPI/Razorpay-centric and settles in INR, not a stablecoin rail.

## Tests

```bash
python3 -m pytest tests/ -v
```

Runs the spending-envelope gate tests standalone — no server, no credentials needed.
