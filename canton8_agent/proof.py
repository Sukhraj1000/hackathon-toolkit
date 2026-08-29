"""Automated LocalNet proof of the wallet's adversarial boundaries."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

import c8lab

from .agent import command_id_for
from .errors import AgentError, SubmissionError
from .ledger import C8LedgerClient, MANDATE
from .localnet_demo import LocalNetDemoResult, run_localnet_demo
from .models import PurchaseRequest
from .resolver import C8TokenResolver


@dataclass(frozen=True)
class ProofStep:
    id: str
    title: str
    status: str
    detail: str
    boundary: str


@dataclass(frozen=True)
class ProofResult:
    mandate_id: str
    owner: str
    agent: str
    merchant: str
    instrument_id: str
    legitimate_receipt: str
    spent: Decimal
    total_cap: Decimal
    receipt_count: int
    revoked: bool
    steps: tuple[ProofStep, ...]


def _detail(exc: Exception) -> str:
    value = " ".join(str(exc).split())
    return value[:500]


def _expect_rejection(
        steps: list[ProofStep], *, step_id: str, title: str,
        boundary: str, action: Callable[[], object]) -> None:
    try:
        action()
    except (AgentError, SubmissionError, c8lab.LabError) as exc:
        steps.append(ProofStep(
            id=step_id, title=title, status="rejected",
            detail=_detail(exc), boundary=boundary))
        return
    raise c8lab.LabError(f"proof failed: {title} unexpectedly succeeded")


def run_localnet_proof(
        *, deadline_seconds: float = 90,
        progress: Callable[[str], None] = print,
        demo_runner=run_localnet_demo) -> ProofResult:
    """Run one purchase, direct bypasses, owner revocation, and final audit."""
    steps: list[ProofStep] = []
    progress("Provisioning a fresh proof wallet and committing one purchase...")
    demo: LocalNetDemoResult = demo_runner(
        amount=Decimal("0.05"), total_cap=Decimal("0.20"),
        deadline_seconds=deadline_seconds, progress=progress)
    steps.append(ProofStep(
        id="purchase", title="Autonomous purchase committed",
        status="committed", detail=(
            f"0.05 {demo.instrument_id}; receipt {demo.receipt_contract_id}"),
        boundary="atomic Canton transaction"))

    ledger = C8LedgerClient(demo.agent, demo.agent_user)
    resolver = C8TokenResolver(demo.resolver_user)
    authorization = ledger.current_authorization(demo.mandate_id)
    receipts_before = ledger.list_receipts(demo.mandate_id)
    if len(receipts_before) != 1:
        raise c8lab.LabError(
            f"proof expected one legitimate receipt, found {len(receipts_before)}")

    # Resolve valid transfer inputs once. The attacks bypass MandateAgent and
    # submit straight through the narrow ledger adapter as the agent user.
    valid_request = PurchaseRequest(
        merchant=demo.merchant, amount=Decimal("0.01"),
        business_reference=f"proof-valid-{demo.mandate_id[-10:]}")
    valid_resolution = resolver.resolve(authorization, valid_request)

    progress("Submitting an over-cap charge directly to the ledger...")
    over_cap_request = PurchaseRequest(
        merchant=demo.merchant,
        amount=(authorization.total_cap - authorization.spent
                + Decimal("0.01")),
        business_reference=f"proof-over-cap-{demo.mandate_id[-10:]}")
    over_cap_resolution = resolver.resolve(authorization, over_cap_request)
    _expect_rejection(
        steps, step_id="over-cap", title="Over-cap bypass blocked",
        boundary="Daml totalCap assertion",
        action=lambda: ledger.submit_charge(
            authorization, over_cap_request, over_cap_resolution,
            command_id_for(
                authorization.mandate_id,
                over_cap_request.business_reference)))

    progress("Submitting an unapproved counterparty directly to the ledger...")
    wrong_merchant_request = PurchaseRequest(
        merchant=demo.owner, amount=Decimal("0.01"),
        business_reference=f"proof-wrong-party-{demo.mandate_id[-10:]}")
    _expect_rejection(
        steps, step_id="wrong-counterparty",
        title="Unapproved counterparty blocked",
        boundary="Daml allowedCounterparties assertion",
        action=lambda: ledger.submit_charge(
            authorization, wrong_merchant_request, valid_resolution,
            command_id_for(
                authorization.mandate_id,
                wrong_merchant_request.business_reference)))

    progress("Proving the agent cannot revoke its own mandate...")
    _expect_rejection(
        steps, step_id="agent-revoke",
        title="Agent revoke attempt blocked",
        boundary="Daml owner controller",
        action=lambda: c8lab.submit(
            [{"ExerciseCommand": {
                "templateId": MANDATE,
                "contractId": authorization.mandate_cid,
                "choice": "Revoke",
                "choiceArgument": {},
            }}], act_as=demo.agent, sub=demo.agent_user))

    progress("Revoking the mandate with the isolated owner identity...")
    c8lab.submit(
        [{"ExerciseCommand": {
            "templateId": MANDATE,
            "contractId": authorization.mandate_cid,
            "choice": "Revoke",
            "choiceArgument": {},
        }}], act_as=demo.owner, sub=demo.owner_user)
    steps.append(ProofStep(
        id="owner-revoke", title="Owner revoked mandate",
        status="committed", detail="Static mandate archived on Canton",
        boundary="owner-only Daml Revoke choice"))

    progress("Submitting a final charge after revocation...")
    _expect_rejection(
        steps, step_id="after-revoke",
        title="Post-revocation charge blocked",
        boundary="Daml fetch of archived mandate",
        action=lambda: ledger.submit_charge(
            authorization, valid_request, valid_resolution,
            command_id_for(
                authorization.mandate_id,
                valid_request.business_reference)))

    terminal_authorization = ledger.current_authorization(demo.mandate_id)
    if not terminal_authorization.revoked:
        raise c8lab.LabError(
            "revoked mandate was not visible as terminal audit state")
    receipts_after = ledger.list_receipts(demo.mandate_id)
    if len(receipts_after) != len(receipts_before):
        raise c8lab.LabError(
            "rejected proof attempts changed the committed receipt statement")
    steps.append(ProofStep(
        id="audit", title="Final statement unchanged",
        status="verified",
        detail=(
            f"revoked policy plus {len(receipts_after)} committed receipt; "
            "rejected attempts wrote none"),
        boundary="ledger-derived terminal audit statement"))

    return ProofResult(
        mandate_id=demo.mandate_id, owner=demo.owner, agent=demo.agent,
        merchant=demo.merchant, instrument_id=demo.instrument_id,
        legitimate_receipt=demo.receipt_contract_id,
        spent=terminal_authorization.spent,
        total_cap=terminal_authorization.total_cap,
        receipt_count=len(receipts_after),
        revoked=terminal_authorization.revoked,
        steps=tuple(steps))
