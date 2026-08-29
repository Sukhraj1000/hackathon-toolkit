"""Deterministic offer selection; ledger validation remains authoritative."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .models import Authorization, PurchaseRequest


@dataclass(frozen=True)
class Offer:
    merchant: str
    amount: Decimal
    business_reference: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class LowestPriceDecision:
    def choose(
            self, offers: Sequence[Offer],
            authorization: Authorization) -> PurchaseRequest | None:
        remaining = authorization.total_cap - authorization.spent
        compatible = [
            offer for offer in offers
            if offer.merchant in authorization.allowed_counterparties
            and Decimal("0") < offer.amount <= remaining
            and offer.business_reference
            and offer.business_reference
                not in authorization.processed_references
        ]
        if not compatible:
            return None
        selected = min(
            compatible,
            key=lambda offer: (
                offer.amount, offer.merchant, offer.business_reference))
        return PurchaseRequest(
            merchant=selected.merchant,
            amount=selected.amount,
            business_reference=selected.business_reference)
