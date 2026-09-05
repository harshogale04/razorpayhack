"""
Thin wrapper around the Razorpay test-mode API.

MOCK_MODE=true (the default until you have real credentials) simulates
Razorpay's responses so the rest of the system - catalog, intent handling,
safety gate, audit log - is fully buildable and demoable today. Flip
MOCK_MODE=false once RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are set and every
call here goes to the real test-mode API instead.

Two specific test-mode failure paths are wired in deliberately, because the
brief requires demonstrating at least one being caught live:
  - simulate_network_timeout: mimics a request that never comes back
  - simulate_card_decline: uses Razorpay's documented test card for
    "insufficient funds" once MOCK_MODE=false
"""
import os
import uuid
import time


class PaymentTimeoutError(Exception):
    pass


class PaymentDeclinedError(Exception):
    def __init__(self, message, decline_code=None):
        super().__init__(message)
        self.decline_code = decline_code


def _mock_mode() -> bool:
    return os.environ.get("MOCK_MODE", "true").lower() == "true"


def _get_client():
    import razorpay
    key_id = os.environ["RAZORPAY_KEY_ID"]
    key_secret = os.environ["RAZORPAY_KEY_SECRET"]
    return razorpay.Client(auth=(key_id, key_secret))


def create_order(amount_paise: int, receipt: str, notes: dict = None):
    if _mock_mode():
        return {
            "id": f"order_mock_{uuid.uuid4().hex[:14]}",
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "status": "created",
            "notes": notes or {},
        }
    client = _get_client()
    return client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "notes": notes or {},
    })


def capture_payment(payment_id: str, amount_paise: int, simulate_failure: str = None):
    """
    simulate_failure: None | 'timeout' | 'decline' - lets the demo trigger a
    failure on command without waiting for a real one to occur.
    """
    if simulate_failure == "timeout":
        time.sleep(0.3)  # brief pause so the demo can narrate what's happening
        raise PaymentTimeoutError(f"Network timeout while capturing payment {payment_id}")

    if simulate_failure == "decline":
        raise PaymentDeclinedError(
            f"Payment {payment_id} declined: insufficient funds",
            decline_code="insufficient_funds",
        )

    if _mock_mode():
        return {
            "id": payment_id,
            "amount": amount_paise,
            "status": "captured",
        }

    client = _get_client()
    return client.payment.capture(payment_id, amount_paise)
