"""
Shared order-processing core.

Both entry points into this system - the raw ACP-style /purchase-intent API
(for agents hitting the API directly) and the storefront /checkout endpoint
(for a browsing agent clicking through a rendered page) - route through this
single function. That's deliberate: there is exactly one path that reaches
Razorpay, and exactly one place the spending envelope gate lives, no matter
which front door the request came through.
"""
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app import catalog, audit, razorpay_client
from app.safety import check_spending_envelope


class OrderError(Exception):
    """Raised for any failure/halt in order processing. Carries enough
    context for the caller to build the right HTTP response."""
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self.payload = payload
        super().__init__(str(payload))


@dataclass
class CartItem:
    product_id: str
    quantity: int


def process_order(
    items: list,
    buyer_agent_id: str,
    payment_credential: str,
    simulate_failure: Optional[str] = None,
) -> dict:
    """
    items: list of CartItem
    Returns a success payload dict, or raises OrderError.
    """
    order_ref = f"order_{uuid.uuid4().hex[:10]}"

    audit.log_event(
        event_type="intent_received",
        decision="received",
        order_ref=order_ref,
        payload={
            "items": [{"product_id": i.product_id, "quantity": i.quantity} for i in items],
            "buyer_agent_id": buyer_agent_id,
        },
    )

    # --- Validate every line item and compute the total ---
    line_items = []
    amount_paise = 0
    for item in items:
        product = catalog.get_product(item.product_id)
        if product is None:
            audit.log_event(
                event_type="intent_received", decision="rejected",
                reason=f"Unknown product_id {item.product_id}", order_ref=order_ref,
            )
            raise OrderError(404, {"status": "rejected", "reason": f"Unknown product_id {item.product_id}", "order_ref": order_ref})

        if product["stock"] < item.quantity:
            audit.log_event(
                event_type="stock_check", decision="rejected",
                reason=f"Requested {item.quantity} of {item.product_id}, only {product['stock']} in stock",
                order_ref=order_ref,
            )
            raise OrderError(409, {"status": "rejected", "reason": "Insufficient stock", "order_ref": order_ref})

        line_total = product["price_paise"] * item.quantity
        amount_paise += line_total
        line_items.append({"product_id": item.product_id, "sku": product["sku"], "quantity": item.quantity, "line_total_paise": line_total})

    # --- Non-negotiable safety gate. Pure code, no LLM in this decision. ---
    envelope_decision = check_spending_envelope(amount_paise)
    audit.log_event(
        event_type="envelope_check",
        decision="allowed" if envelope_decision.allowed else "blocked",
        reason=envelope_decision.reason,
        order_ref=order_ref,
        amount_paise=amount_paise,
    )

    if not envelope_decision.allowed:
        print(f"[APPROVAL REQUIRED] order={order_ref} reason={envelope_decision.reason}")
        audit.log_event(
            event_type="halted_for_approval", decision="pending_approval",
            reason=envelope_decision.reason, order_ref=order_ref, amount_paise=amount_paise,
        )
        raise OrderError(202, {
            "status": "halted_for_human_approval",
            "reason": envelope_decision.reason,
            "order_ref": order_ref,
            "amount_paise": amount_paise,
        })

    # --- Envelope passed. Proceed to Razorpay test-mode order + capture. ---
    try:
        order = razorpay_client.create_order(amount_paise, receipt=order_ref, notes={"buyer_agent_id": buyer_agent_id})
        audit.log_event(
            event_type="razorpay_order_created", decision="success",
            order_ref=order_ref, amount_paise=amount_paise, payload=order,
        )

        payment_id = f"pay_{uuid.uuid4().hex[:14]}"
        payment = razorpay_client.capture_payment(payment_id, amount_paise, simulate_failure=simulate_failure)

        for item in items:
            catalog.decrement_stock(item.product_id, item.quantity)

        audit.log_event(
            event_type="payment_captured", decision="success",
            order_ref=order_ref, amount_paise=amount_paise, payload=payment,
        )

        return {
            "status": "success",
            "order_ref": order_ref,
            "razorpay_order_id": order["id"],
            "payment_id": payment_id,
            "amount_paise": amount_paise,
            "items": line_items,
        }

    except razorpay_client.PaymentTimeoutError as e:
        audit.log_event(
            event_type="payment_failed", decision="failure", reason=str(e),
            order_ref=order_ref, amount_paise=amount_paise,
        )
        raise OrderError(504, {"status": "failed_timeout", "reason": str(e), "order_ref": order_ref})

    except razorpay_client.PaymentDeclinedError as e:
        audit.log_event(
            event_type="payment_failed", decision="failure", reason=str(e),
            order_ref=order_ref, amount_paise=amount_paise, payload={"decline_code": e.decline_code},
        )
        raise OrderError(402, {"status": "declined", "reason": str(e), "order_ref": order_ref})