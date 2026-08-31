"""One-command LocalNet demonstration of an atomic mandate purchase.

This module is intentionally operator-side demo code. It provisions fresh
LocalNet identities, including the read-only owner resolver, and never writes
credentials to disk. The reusable wallet and resolver behavior remains in the
small modules next to this one.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from decimal import Decimal
from pathlib import Path
import os
import subprocess
import tempfile
import time
from typing import Callable, Mapping
import urllib.parse
import uuid

import c8lab

from .agent import MandateAgent, command_id_for
from .errors import ResolutionError, SubmissionError
from .ledger import C8LedgerClient
from .models import PurchaseRequest
from .resolver import C8TokenResolver


MANDATE_PROPOSAL = "#c8-agent-wallet:Mandate:MandateProposal"


@dataclass(frozen=True)
class LocalNetDemoResult:
    mandate_id: str
    owner: str
    agent: str
    merchant: str
    owner_user: str
    agent_user: str
    merchant_user: str
    resolver_user: str
    instrument_id: str
    amount: Decimal
    total_cap: Decimal
    spent: Decimal
    remaining: Decimal
    receipt_contract_id: str
    command_id: str
    ledger_update_id: str
    over_cap_error: str


def _right(kind: str, party: str):
    return {"kind": {kind: {"value": {"party": party}}}}


def _create_user(user_id: str, primary_party: str, rights) -> None:
    c8lab.call(
        "/v2/users",
        {"user": {"id": user_id,
                  "primaryParty": primary_party,
                  "isDeactivated": False,
                  "identityProviderId": ""},
         "rights": rights},
        sub=c8lab.ADMIN)


def _active_events(party: str, template_id: str, user_id: str):
    body = {"filter": {"filtersByParty": {party: {"cumulative": [
                {"identifierFilter": {"TemplateFilter": {"value": {
                    "templateId": template_id,
                    "includeCreatedEventBlob": False}}}}]}}},
            "verbose": False,
            "activeAtOffset": c8lab.ledger_end(user_id)}
    events = []
    for item in c8lab.call("/v2/state/active-contracts", body, sub=user_id):
        event = (item.get("contractEntry", {})
                 .get("JsActiveContract", {}).get("createdEvent"))
        if event:
            events.append(event)
    return events


def _only_contract_id(party: str, template_id: str, user_id: str) -> str:
    events = _active_events(party, template_id, user_id)
    if len(events) != 1:
        raise c8lab.LabError(
            f"expected one active {template_id}, found {len(events)}")
    return events[0]["contractId"]


def _upload_mandate_dar(root: Path) -> None:
    package_dir = root / "daml-starter"
    try:
        subprocess.run(
            ["daml", "build"], cwd=package_dir, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        dar = package_dir / ".daml/dist/c8-agent-wallet-1.0.1.dar"
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8") as token_file:
            token_file.write(c8lab.token(c8lab.ADMIN))
            token_file.flush()
            subprocess.run(
                ["daml", "ledger", "upload-dar",
                 "--host", os.getenv("C8_GRPC_HOST", "127.0.0.1"),
                 "--port", os.getenv("C8_GRPC_PORT", "2901"),
                 "--access-token-file", token_file.name,
                 str(dar)],
                cwd=root, check=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError as exc:
        raise c8lab.LabError(
            "the Daml CLI is required for the MVP; install it per SETUP.md") \
            from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.stdout or "").strip()
        detail = f"\n  {output[-1000:]}" if output else ""
        raise c8lab.LabError(
            f"could not build or upload the mandate DAR{detail}") from exc


def _fund_owner(
        provider: str, owner: str, amount: Decimal,
        owner_user: str, deadline_seconds: float,
        sleeper: Callable[[float], None]):
    deadline = time.monotonic() + deadline_seconds
    while True:
        try:
            funding = c8lab.transfer(
                provider, owner, str(amount), sub=c8lab.USER)
            break
        except c8lab.LabError as exc:
            contention_markers = (
                "LOCAL_VERDICT_LOCKED_CONTRACTS",
                "LOCAL_VERDICT_INACTIVE_CONTRACTS",
                "CONTRACT_NOT_FOUND",
                "INCONSISTENT",
            )
            if (not any(marker in str(exc) for marker in contention_markers)
                    or time.monotonic() >= deadline):
                raise
            sleeper(2)
    if funding["transferKind"] == "offer":
        instruction_cid = funding.get("instructionCid")
        if not instruction_cid:
            raise c8lab.LabError(
                "owner funding returned an offer without an instruction ID")
        c8lab.accept_transfer(instruction_cid, owner, sub=owner_user)


def _wait_for_direct(
        resolver: C8TokenResolver, authorization,
        request: PurchaseRequest, deadline_seconds: float,
        sleeper: Callable[[float], None]) -> None:
    deadline = time.monotonic() + deadline_seconds
    last_result = "not queried"
    while time.monotonic() < deadline:
        try:
            result = resolver.resolve(authorization, request)
            last_result = result.transfer_kind
            if result.transfer_kind == "direct":
                return
        except ResolutionError as exc:
            last_result = str(exc)
            if not exc.retryable:
                raise
        sleeper(2)
    raise c8lab.LabError(
        "merchant preapproval did not become ready for a direct transfer; "
        f"last result: {last_result}")


def _ledger_update_id(transaction: Mapping) -> str:
    value = transaction.get("transaction", transaction)
    if not isinstance(value, Mapping):
        return ""
    for key in ("updateId", "transactionId", "offset"):
        if value.get(key):
            return str(value[key])
    return ""


def run_localnet_demo(
        *, amount: Decimal = Decimal("0.1"),
        total_cap: Decimal = Decimal("1.0"),
        deadline_seconds: float = 90,
        root: Path | None = None,
        progress: Callable[[str], None] = print,
        sleeper: Callable[[float], None] = time.sleep) -> LocalNetDemoResult:
    """Provision fresh demo state, make one purchase, and reject overspending."""
    if amount <= 0:
        raise ValueError("purchase amount must be positive")
    if total_cap <= amount:
        raise ValueError("mandate cap must be greater than the purchase amount")
    if deadline_seconds <= 0:
        raise ValueError("deadline must be positive")
    if c8lab.IDP or c8lab.ACCESS_TOKEN:
        raise c8lab.LabError(
            "the MVP command is LocalNet-only; unset C8_IDP and "
            "C8_ACCESS_TOKEN")

    root = root or Path(__file__).resolve().parents[1]
    progress("Building and uploading the mandate DAR...")
    _upload_mandate_dar(root)

    run_id = uuid.uuid4().hex[:10]
    owner_user = f"mvp-owner-{run_id}"
    agent_user = f"mvp-agent-{run_id}"
    merchant_user = f"mvp-merchant-{run_id}"
    resolver_user = f"mvp-resolver-{run_id}"

    progress("Provisioning fresh least-privilege LocalNet identities...")
    owner = c8lab.allocate_party(owner_user, sub=c8lab.ADMIN, grant_to=None)
    agent = c8lab.allocate_party(agent_user, sub=c8lab.ADMIN, grant_to=None)
    merchant = c8lab.allocate_party(
        merchant_user, sub=c8lab.ADMIN, grant_to=None)
    _create_user(owner_user, owner, [_right("CanActAs", owner)])
    _create_user(agent_user, agent, [_right("CanActAs", agent)])
    _create_user(merchant_user, merchant, [_right("CanActAs", merchant)])
    _create_user(resolver_user, owner, [_right("CanReadAs", owner)])

    provider = c8lab.find_party("app_user", sub=c8lab.ADMIN)
    c8lab.create_preapproval_proposal(owner, provider, sub=owner_user)
    c8lab.create_preapproval_proposal(merchant, provider, sub=merchant_user)
    _fund_owner(
        provider, owner, max(total_cap + Decimal("0.01"), Decimal("1.0")),
        owner_user,
        deadline_seconds, sleeper)

    instrument_id = "Amulet"
    expected_admin = c8lab.admin_party()
    mandate_id = f"mvp-mandate-{run_id}"
    expires_at = (datetime.datetime.now(datetime.timezone.utc)
                  + datetime.timedelta(hours=1))
    proposal = {
        "mandateId": mandate_id,
        "owner": owner,
        "agent": agent,
        "instrumentId": instrument_id,
        "expectedAdmin": expected_admin,
        "totalCap": str(total_cap),
        "allowedCounterparties": [merchant],
        "expiresAt": expires_at.replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"),
    }
    c8lab.submit(
        [{"CreateCommand": {
            "templateId": MANDATE_PROPOSAL,
            "createArguments": proposal}}],
        act_as=owner, sub=owner_user)
    proposal_cid = _only_contract_id(
        agent, MANDATE_PROPOSAL, agent_user)
    c8lab.submit(
        [{"ExerciseCommand": {
            "templateId": MANDATE_PROPOSAL,
            "contractId": proposal_cid,
            "choice": "Accept",
            "choiceArgument": {}}}],
        act_as=agent, sub=agent_user)

    ledger = C8LedgerClient(agent, agent_user)
    resolver = C8TokenResolver(resolver_user)
    wallet = MandateAgent(agent, ledger, resolver)
    request = PurchaseRequest(
        merchant=merchant,
        amount=amount,
        business_reference=f"mvp-order-{run_id}")
    authorization = ledger.current_authorization(mandate_id)

    progress("Waiting for the merchant preapproval, then purchasing...")
    _wait_for_direct(
        resolver, authorization, request, deadline_seconds, sleeper)
    outcome = wallet.charge(mandate_id, request)
    if outcome.receipt is None:
        raise c8lab.LabError(
            "the charge committed but its receipt was not visible")

    current = ledger.current_authorization(mandate_id)
    remaining = current.total_cap - current.spent
    over_cap_request = PurchaseRequest(
        merchant=merchant,
        amount=remaining + Decimal("0.01"),
        business_reference=f"mvp-over-cap-{run_id}")
    over_cap_resolution = resolver.resolve(current, over_cap_request)
    if over_cap_resolution.transfer_kind != "direct":
        raise c8lab.LabError(
            "over-cap proof could not obtain direct transfer context")
    try:
        # Deliberately bypass MandateAgent's local checks. The direct ledger
        # submission must be rejected by MandateUsage.Charge itself.
        ledger.submit_charge(
            current, over_cap_request, over_cap_resolution,
            command_id_for(mandate_id, over_cap_request.business_reference))
    except SubmissionError as exc:
        over_cap_error = str(exc)
    else:
        raise c8lab.LabError(
            "the direct on-ledger over-cap proof unexpectedly succeeded")

    return LocalNetDemoResult(
        mandate_id=mandate_id,
        owner=owner,
        agent=agent,
        merchant=merchant,
        owner_user=owner_user,
        agent_user=agent_user,
        merchant_user=merchant_user,
        resolver_user=resolver_user,
        instrument_id=current.instrument_id,
        amount=amount,
        total_cap=current.total_cap,
        spent=current.spent,
        remaining=remaining,
        receipt_contract_id=outcome.receipt.contract_id,
        command_id=outcome.command_id,
        ledger_update_id=_ledger_update_id(outcome.transaction),
        over_cap_error=over_cap_error)
