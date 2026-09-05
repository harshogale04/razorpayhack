"""
Visual browsing agent.

Unlike buyer_agent.py (which calls your API directly), this script drives a
REAL browser against the rendered storefront: it takes screenshots, sends
them to Gemini's vision model, gets back a decision, and executes that
decision as an actual Playwright click on the actual page.

CURSOR VISIBILITY: Playwright doesn't move your actual OS mouse pointer -
clicks are simulated at the browser/page level, so by default there's
nothing to visually track. To fix that, this script injects a small
on-page "fake cursor" element and smoothly animates it toward each target
before clicking (with a little pulse on click). This shows up in the
browser window itself, so it's visible regardless of what screen recording
tool you use - more reliable than depending on the real OS cursor.

Grounding: alongside each screenshot, the script also pulls a list of
currently-clickable elements from the page (their data-agent-action,
product_id, and visible label). Gemini looks at the screenshot to reason
("this mug looks affordable"), but must choose its action from that exact
list - so the click always lands on a real, current DOM element, never a
guessed coordinate.

Run this AFTER your server is up. It opens a REAL visible browser window
(headed mode) so you can watch it live during a demo.

First-time setup:
    pip install playwright google-generativeai python-dotenv
    playwright install chromium

Requires GEMINI_API_KEY in .env.
"""
import os
import json
import time
import io
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from PIL import Image

load_dotenv()

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8000")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
BUDGET_PAISE = int(os.environ.get("BUYER_BUDGET_PAISE", 400000))  # default INR 4000
MAX_STEPS = int(os.environ.get("BROWSING_MAX_STEPS", 9))
SIMULATE_FAILURE = os.environ.get("BROWSING_SIMULATE_FAILURE")  # None | "timeout" | "decline"
CURSOR_MOVE_MS = int(os.environ.get("BROWSING_CURSOR_MOVE_MS", 280))  # how long each cursor glide takes
NARRATE_DELAY = float(os.environ.get("BROWSING_NARRATE_DELAY", 0.15))  # pause after each printed line
SCREENSHOT_MAX_WIDTH = int(os.environ.get("BROWSING_SCREENSHOT_WIDTH", 640))  # downscaled before sending to Gemini

CURSOR_CSS = """
#agent-cursor {
  position: fixed; top: 0; left: 0; width: 22px; height: 22px;
  pointer-events: none; z-index: 999999;
  background: radial-gradient(circle, rgba(200,255,77,0.95) 0%, rgba(200,255,77,0.25) 60%, transparent 72%);
  border: 2px solid #c8ff4d;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  transition: none;
  box-shadow: 0 0 12px rgba(200,255,77,0.6);
}
#agent-cursor.clicking { background: rgba(200,255,77,0.75); transform: translate(-50%, -50%) scale(0.7); }
body.agent-driving, body.agent-driving * { cursor: none !important; }
"""

CURSOR_INIT_JS = """
() => {
  if (document.getElementById('agent-cursor')) return;
  document.body.classList.add('agent-driving');
  const el = document.createElement('div');
  el.id = 'agent-cursor';
  document.body.appendChild(el);
  window.__agentCursorPos = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
  el.style.left = window.__agentCursorPos.x + 'px';
  el.style.top = window.__agentCursorPos.y + 'px';

  window.moveAgentCursorTo = (x, y, duration) => {
    return new Promise(resolve => {
      const cursor = document.getElementById('agent-cursor');
      const start = window.__agentCursorPos;
      const startTime = performance.now();
      function step(now) {
        const t = Math.min(1, (now - startTime) / duration);
        const eased = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
        const curX = start.x + (x - start.x) * eased;
        const curY = start.y + (y - start.y) * eased;
        cursor.style.left = curX + 'px';
        cursor.style.top = curY + 'px';
        if (t < 1) {
          requestAnimationFrame(step);
        } else {
          window.__agentCursorPos = { x, y };
          resolve();
        }
      }
      requestAnimationFrame(step);
    });
  };

  window.agentCursorClickPulse = () => {
    const cursor = document.getElementById('agent-cursor');
    cursor.classList.add('clicking');
    setTimeout(() => cursor.classList.remove('clicking'), 220);
  };
}
"""


def narrate(msg, delay=None):
    print(msg)
    time.sleep(NARRATE_DELAY if delay is None else delay)


def downscale_for_gemini(screenshot_bytes):
    """
    The browser itself stays full resolution (so the demo looks sharp),
    but a smaller image sent to Gemini means less to process and a
    noticeably faster response, with no real loss in decision quality.
    """
    img = Image.open(io.BytesIO(screenshot_bytes))
    if img.width > SCREENSHOT_MAX_WIDTH:
        ratio = SCREENSHOT_MAX_WIDTH / img.width
        img = img.resize((SCREENSHOT_MAX_WIDTH, int(img.height * ratio)))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def inject_cursor(page):
    page.add_style_tag(content=CURSOR_CSS)
    page.evaluate(CURSOR_INIT_JS)


def move_and_click(page, element_id):
    """
    Animates the fake cursor to the element's center, pulses it, then
    performs a real coordinate-based click there. Re-injects the cursor
    if a page navigation/re-render wiped it out.
    """
    locator = page.locator(f"#{element_id}")
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if box is None:
        raise RuntimeError(f"Element #{element_id} has no bounding box (not visible)")

    target_x = box["x"] + box["width"] / 2
    target_y = box["y"] + box["height"] / 2

    if page.evaluate("() => !document.getElementById('agent-cursor')"):
        inject_cursor(page)

    page.evaluate("([x, y, d]) => window.moveAgentCursorTo(x, y, d)", [target_x, target_y, CURSOR_MOVE_MS])
    page.evaluate("() => window.agentCursorClickPulse()")
    page.mouse.move(target_x, target_y)
    page.mouse.down()
    time.sleep(0.05)
    page.mouse.up()
    time.sleep(0.12)


def get_clickable_elements(page):
    return page.eval_on_selector_all(
        "[data-agent-action]",
        """els => els.map(el => ({
            id: el.id,
            action: el.dataset.agentAction,
            productId: el.dataset.productId || null,
            label: el.innerText.trim().replace(/\\s+/g, ' '),
            disabled: el.disabled || false
        })).filter(e => !e.disabled && e.id)"""
    )


def ask_gemini_for_action(screenshot_bytes, clickable_elements, budget_paise, cart_so_far, step, max_steps, max_retries=3):
    import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set - add it to .env")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    prompt = f"""You are an AI agent browsing a real shopping website on behalf of a
user, looking at a screenshot of the actual page state right now.

Budget: INR {budget_paise/100:.2f} total.
Items already added to cart this session: {json.dumps(cart_so_far)}
Step {step + 1} of {max_steps} (you must reach payment before running out of steps).

Elements you can currently click, by id (choose from this list ONLY):
{json.dumps(clickable_elements, indent=2)}

Look at the screenshot and decide your next single action. Respond with
ONLY a JSON object, no other text, in this exact shape:
{{"element_id": "the id from the list above", "reason": "one short sentence explaining the decision from what you see on screen"}}

IMPORTANT - budget your steps: completing checkout takes exactly 3 actions
AFTER your cart is ready - view cart, proceed to checkout, then pay now.
So if you're on step {step + 1} of {max_steps}, you must stop adding items
and start checking out once at most {max(1, max_steps - step - 3)} more
add-to-cart actions remain. Prefer a cart of just 2 items - that is
enough to demonstrate the flow and leaves plenty of steps to reach payment
safely. Do not keep adding items just because budget remains.
"""

    image_part = {"mime_type": "image/png", "data": screenshot_bytes}

    for attempt in range(max_retries):
        try:
            response = model.generate_content([prompt, image_part])
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            is_rate_limit = "429" in str(e) or "quota" in str(e).lower() or "ResourceExhausted" in type(e).__name__
            if is_rate_limit and attempt < max_retries - 1:
                wait_s = 25  # Gemini's free-tier error usually suggests ~20-25s
                print(f"  [rate limited - waiting {wait_s}s before retry {attempt + 2}/{max_retries}]")
                time.sleep(wait_s)
                continue
            raise


def main():
    narrate("Visual browsing agent starting...", 0.5)
    narrate(f"Budget: INR {BUDGET_PAISE/100:.2f}")

    query = "?agent_id=gemini-vision-agent-1"
    if SIMULATE_FAILURE:
        query += f"&simulate_failure={SIMULATE_FAILURE}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{SERVER_URL}/storefront/{query}")
        page.wait_for_selector("#product-grid .card")
        inject_cursor(page)

        narrate("Storefront loaded. Beginning to browse...")

        cart_so_far = []
        checked_out = False

        for step in range(MAX_STEPS):
            screenshot_bytes = page.screenshot()
            gemini_bytes = downscale_for_gemini(screenshot_bytes)
            clickable = get_clickable_elements(page)

            if not clickable:
                narrate("No clickable elements found - stopping.")
                break

            try:
                decision = ask_gemini_for_action(
                    gemini_bytes, clickable, BUDGET_PAISE, cart_so_far, step, MAX_STEPS
                )
            except Exception as e:
                print(f"Gemini decision failed: {e}")
                break

            target = next((e for e in clickable if e["id"] == decision.get("element_id")), None)
            if target is None:
                narrate(f"  Gemini picked an invalid element_id ({decision.get('element_id')}) - stopping.")
                break

            narrate(f"  Step {step+1}: {target['action']} \"{target['label']}\" - {decision.get('reason', '')}", 0.4)

            move_and_click(page, target["id"])

            if target["action"] == "add-to-cart":
                cart_so_far.append(target["productId"])
            elif target["action"] == "proceed-to-checkout":
                time.sleep(0.25)  # let the payment sheet render before next screenshot
            elif target["action"] == "pay-now":
                checked_out = True
                time.sleep(0.8)  # let the result banner render
                break

        if checked_out:
            banner_text = page.inner_text("#result-banner")
            narrate("")
            narrate("--- Checkout result ---", 0.3)
            print(banner_text)
        else:
            narrate("Session ended without completing checkout.")

        narrate("")
        narrate("Leaving browser open for 2 seconds so you can see the final state...", 0)
        time.sleep(2)
        browser.close()


if __name__ == "__main__":
    main()