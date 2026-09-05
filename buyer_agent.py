"""
Buyer agent demo script.

This simulates the external AI shopping agent from the outside: it hits your
running server's public endpoints exactly like a real third-party agent
would (no shortcuts, no internal imports from `app/`). It:

  1. Fetches the agent-readable catalog
  2. Asks Gemini to pick a small cart within a budget, with reasoning
  3. Narrates the picks out loud (for the live demo)
  4. Checks out each cart item as a separate purchase-intent call against
     your running server - so every item still passes through the real
     spending envelope gate, audit log, etc. Nothing here bypasses safety.

Run this AFTER your server is up (uvicorn app.main:app --port 8000) and
keep the dashboard open in a browser to watch it happen live.

Requires: pip install google-generativeai requests python-dotenv
Requires: GEMINI_API_KEY set in .env (or exported in your shell)
"""
import os
import sys
import time
import json
import requests
from dotenv import load_dotenv

load_dotenv()

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8000")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
BUYER_AGENT_ID = "agent-demo-gemini-1"
BUDGET_PAISE = int(os.environ.get("BUYER_BUDGET_PAISE", 400000))  # default INR 4000


def narrate(msg, delay=0.9):
    print(msg)
    time.sleep(delay)


def get_catalog():
    resp = requests.get(f"{SERVER_URL}/ai-catalog.json")
    resp.raise_for_status()
    return resp.json()["products"]


def ask_gemini_for_cart(catalog, budget_paise):
    """
    Asks Gemini to pick 2-3 sensible items within budget, with a one-line
    reason for each. Returns a list of {product_id, quantity, reason}.
    """
    import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set - add it to .env")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    prompt = f"""You are an AI shopping agent buying on behalf of a user.
Budget: {budget_paise / 100:.2f} INR total.

Catalog (JSON):
{json.dumps(catalog, indent=2)}

Pick 2-3 items that make sense together, staying at or under the total
budget. Respond with ONLY a JSON array, no other text, in this exact shape:
[{{"product_id": "...", "quantity": 1, "reason": "one short sentence"}}]
"""

    response = model.generate_content(prompt)
    text = response.text.strip()
    # Strip markdown code fences if Gemini wraps the JSON in them
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def checkout_cart(cart, catalog_by_id):
    print()
    narrate(f"--- Checking out {len(cart)} item(s) ---", 0.6)
    for item in cart:
        product = catalog_by_id.get(item["product_id"])
        if product is None:
            narrate(f"  [skip] unknown product_id {item['product_id']}")
            continue

        line_total = product["price_paise"] * item["quantity"]
        narrate(
            f"  -> Submitting intent: {item['quantity']} x {product['sku']} "
            f"(₹{line_total/100:.2f}) - {item['reason']}",
            0.6,
        )

        resp = requests.post(
            f"{SERVER_URL}/purchase-intent",
            json={
                "intent": "purchase",
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "buyer_agent_id": BUYER_AGENT_ID,
                "payment_credential": "tok_mock_demo",
            },
        )

        if resp.status_code == 200:
            narrate(f"     [OK] {resp.json()['status']} - order_ref {resp.json()['order_ref']}", 0.4)
        else:
            body = resp.json()
            detail = body.get("detail", body)
            narrate(f"     [HALTED/FAILED - {resp.status_code}] {detail}", 0.4)


def main():
    narrate("AI buyer agent starting up...", 0.5)
    narrate(f"Budget for this session: INR {BUDGET_PAISE/100:.2f}")
    narrate("")

    narrate("Fetching agent-readable catalog...")
    catalog = get_catalog()
    catalog_by_id = {p["product_id"]: p for p in catalog}
    narrate(f"Catalog loaded: {len(catalog)} products available.")
    narrate("")

    narrate("Reasoning about what to buy (Gemini)...")
    try:
        cart = ask_gemini_for_cart(catalog, BUDGET_PAISE)
    except Exception as e:
        print(f"Gemini call failed: {e}")
        sys.exit(1)

    narrate("Cart decided:")
    for item in cart:
        p = catalog_by_id.get(item["product_id"], {})
        narrate(f"  + {item['quantity']} x {p.get('sku', item['product_id'])} - {item['reason']}", 0.5)

    checkout_cart(cart, catalog_by_id)

    narrate("")
    narrate("Session complete. Check the dashboard for the full audit trail.")


if __name__ == "__main__":
    main()