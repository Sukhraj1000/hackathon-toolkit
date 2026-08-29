"""Safe orchestration for one ledger-enforced mandate charge."""

from datetime import datetime, timezone
from hashlib import sha256
import time
from typing import Callable, Protocol

from .errors import AgentError, ResolutionError, SubmissionError
from .models import (
    Authorization, ChargeOutcome, PurchaseRequest, Receipt, ResolvedCharge,
)


class LedgerGateway(Protocol):
    def current_authorization(self, mandate_id: str) -> Authorization: ...
    def find_receipt(
            self, mandate_id: str, business_reference: str) -> Receipt | None: ...
    def submit_charge(
            self, authorization: Authorization, request: PurchaseRequest,
            resolved: ResolvedCharge, command_id: str): ...


class ResolverGateway(Protocol):
    def resolve(
            self, authorization: Authorization,
            request: PurchaseRequest) -> ResolvedCharge: ...


class ApprovalGateway(Protocol):
    def approve(
            self, authorization: Authorization,
            request: PurchaseRequest) -> bool: ...


def command_id_for(mandate_id: str, business_reference: str) -> str:
    digest = sha256(
        f"{mandate_id}\0{business_reference}".encode("utf-8")).hexdigest()[:32]
    return f"agent-charge-{digest}"


class MandateAgent:
    def __init__(
            self, agent_party: str, ledger: LedgerGateway,
            resolver: ResolverGateway, *, approval: ApprovalGateway | None = None,
            approval_threshold=None,
            now: Callable[[], datetime] | None = None,
            sleeper: Callable[[float], None] = time.sleep):
        self.agent_party = agent_party
        self.ledger = ledger
        self.resolver = resolver
        self.approval = approval
        self.approval_threshold = approval_threshold
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper

    def _validate(
            self, authorization: Authorization,
            request: PurchaseRequest) -> None:
        if authorization.agent != self.agent_party:
            raise AgentError("configured agent does not match mandate agent")
        if authorization.revoked:
            raise AgentError("mandate is revoked")
        if request.amount <= 0:
            raise AgentError("charge amount must be positive")
        reference = request.business_reference
        if not reference.strip() or len(reference) > 128:
            raise AgentError(
                "business reference must be non-empty and at most 128 symbols")
        if reference in authorization.processed_references:
            raise AgentError("business reference already processed")
        if request.merchant not in authorization.allowed_counterparties:
            raise AgentError("merchant is not allowed by mandate")
        if authorization.spent + request.amount > authorization.total_cap:
            raise AgentError("charge exceeds remaining mandate cap")
        if self.now() >= authorization.expires_at:
            raise AgentError("mandate is expired")

    @staticmethod
    def _outcome_from_receipt(
            receipt: Receipt, request: PurchaseRequest,
            command_id: str) -> ChargeOutcome:
        if (receipt.merchant != request.merchant
                or receipt.amount != request.amount):
            raise AgentError(
                "business reference belongs to a different committed charge")
        return ChargeOutcome(
            status="already_committed", command_id=command_id,
            receipt=receipt)

    def charge(
            self, mandate_id: str, request: PurchaseRequest, *,
            max_attempts: int = 3, backoff_seconds: float = 0.25) -> ChargeOutcome:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        command_id = command_id_for(mandate_id, request.business_reference)

        receipt = self.ledger.find_receipt(
            mandate_id, request.business_reference)
        if receipt:
            return self._outcome_from_receipt(receipt, request, command_id)

        initial_authorization = self.ledger.current_authorization(mandate_id)
        self._validate(initial_authorization, request)
        if (self.approval_threshold is not None
                and request.amount > self.approval_threshold):
            if self.approval is None:
                raise AgentError("owner approval is required but unavailable")
            if not self.approval.approve(initial_authorization, request):
                raise AgentError("owner rejected the proposed charge")

        for attempt in range(max_attempts):
            authorization = (
                initial_authorization if attempt == 0
                else self.ledger.current_authorization(mandate_id))
            self._validate(authorization, request)
            try:
                resolved = self.resolver.resolve(authorization, request)
            except ResolutionError as exc:
                if not exc.retryable or attempt + 1 >= max_attempts:
                    raise
                self.sleeper(backoff_seconds * (2 ** attempt))
                continue
            if resolved.transfer_kind != "direct":
                raise AgentError(
                    "receiver is not preapproved for immediate token settlement")
            try:
                transaction = self.ledger.submit_charge(
                    authorization, request, resolved, command_id)
                return ChargeOutcome(
                    status="committed", command_id=command_id,
                    receipt=self.ledger.find_receipt(
                        mandate_id, request.business_reference),
                    transaction=transaction)
            except SubmissionError as exc:
                receipt = self.ledger.find_receipt(
                    mandate_id, request.business_reference)
                if receipt:
                    return self._outcome_from_receipt(
                        receipt, request, command_id)
                if not exc.retryable or attempt + 1 >= max_attempts:
                    raise
                self.sleeper(backoff_seconds * (2 ** attempt))

        raise AssertionError("unreachable retry loop")
