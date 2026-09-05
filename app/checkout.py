from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.order_processing import process_order, OrderError, CartItem

router = APIRouter()


class CheckoutItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)


class CheckoutRequest(BaseModel):
    items: List[CheckoutItem]
    buyer_agent_id: str
    payment_credential: str
    simulate_failure: Optional[Literal["timeout", "decline"]] = None


@router.post("/checkout")
def checkout(req: CheckoutRequest):
    try:
        result = process_order(
            items=[CartItem(product_id=i.product_id, quantity=i.quantity) for i in req.items],
            buyer_agent_id=req.buyer_agent_id,
            payment_credential=req.payment_credential,
            simulate_failure=req.simulate_failure,
        )
        return result
    except OrderError as e:
        raise HTTPException(status_code=e.status_code, detail=e.payload)