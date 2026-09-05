"""
The spending envelope gate.

This is deliberately a plain Python function with no LLM call anywhere in it.
The whole point of the safety layer is that the "is this allowed" decision is
a structural code-level check, not something a model reasons its way into.

Any amount over the limit must halt and route to human approval - it must
never auto-execute, no matter what the intent payload says.
"""
import os
from dataclasses import dataclass


def get_spending_limit_paise() -> int:
    return int(os.environ.get("SPENDING_LIMIT_PAISE", 500000))  # default INR 5000


@dataclass
class EnvelopeDecision:
    allowed: bool
    amount_paise: int
    limit_paise: int
    reason: str


def check_spending_envelope(amount_paise: int) -> EnvelopeDecision:
    """
    The single choke point every transaction must pass through before any
    Razorpay call is made. Returns an EnvelopeDecision - callers must check
    .allowed and branch to the human-approval path if False.
    """
    limit = get_spending_limit_paise()

    if amount_paise <= 0:
        return EnvelopeDecision(
            allowed=False,
            amount_paise=amount_paise,
            limit_paise=limit,
            reason=f"Invalid amount: {amount_paise} paise",
        )

    if amount_paise > limit:
        return EnvelopeDecision(
            allowed=False,
            amount_paise=amount_paise,
            limit_paise=limit,
            reason=f"Amount {amount_paise} paise exceeds spending envelope of {limit} paise - halted for human approval",
        )

    return EnvelopeDecision(
        allowed=True,
        amount_paise=amount_paise,
        limit_paise=limit,
        reason="Within spending envelope",
    )
