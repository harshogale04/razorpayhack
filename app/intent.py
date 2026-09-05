from fastapi import APIRouter, HTTPException

from app.models import PurchaseIntent
from app.order_processing import process_order, OrderError, CartItem

router = APIRouter()


@router.post("/purchase-intent")
def handle_purchase_intent(intent: PurchaseIntent):
    try:
        result = process_order(
            items=[CartItem(product_id=intent.product_id, quantity=intent.quantity)],
            buyer_agent_id=intent.buyer_agent_id,
            payment_credential=intent.payment_credential,
            simulate_failure=intent.simulate_failure,
        )
        return result
    except OrderError as e:
        raise HTTPException(status_code=e.status_code, detail=e.payload)