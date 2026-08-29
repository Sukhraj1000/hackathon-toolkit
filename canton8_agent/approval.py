"""Small approval adapters; production approval must authenticate the owner."""

from dataclasses import dataclass

from .models import Authorization, PurchaseRequest


@dataclass
class FixedApproval:
    """Deterministic test/demo approval, never a production identity check."""

    approved: bool

    def approve(
            self, authorization: Authorization,
            request: PurchaseRequest) -> bool:
        return self.approved
