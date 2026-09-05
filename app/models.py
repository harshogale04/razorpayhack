from pydantic import BaseModel, Field
from typing import Optional, Literal


class PurchaseIntent(BaseModel):
    """
    Shape follows the ACP (Agentic Commerce Protocol) interaction pattern
    for a structured purchase-intent payload.
    """
    intent: Literal["purchase"]
    product_id: str
    quantity: int = Field(gt=0)
    buyer_agent_id: str
    payment_credential: str  # opaque token in this build - never a raw card number
    simulate_failure: Optional[Literal["timeout", "decline"]] = None  # demo-only field
