"""Agent-only JSON Ledger API adapter for the deployed mandate package."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

import c8lab

from .errors import AgentError, SubmissionError
from .models import Authorization, PurchaseRequest, Receipt, ResolvedCharge


MANDATE = "#daml-starter:Mandate:Mandate"
MANDATE_USAGE = "#daml-starter:Mandate:MandateUsage"
CHARGE_RECEIPT = "#daml-starter:Mandate:ChargeReceipt"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _create_argument(event: Mapping[str, Any]) -> Mapping[str, Any]:
    argument = event.get("createArgument", event.get("createArguments"))
    if not isinstance(argument, Mapping):
        raise AgentError("ledger created event omitted its create argument")
    return argument


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


def _submission_error(exc: c8lab.LabError) -> SubmissionError:
    message = str(exc)
    ambiguous_markers = (
        "cannot reach", "network error", "HTTP 500", "HTTP 502",
        "HTTP 503", "HTTP 504",
    )
    retryable_markers = (
        "LOCAL_VERDICT_LOCKED_CONTRACTS", "CONTRACT_NOT_FOUND",
        "LOCAL_VERDICT_INACTIVE_CONTRACTS", "STALE", "ABORTED",
        "INCONSISTENT",
    )
    ambiguous = any(marker in message for marker in ambiguous_markers)
    retryable = ambiguous or any(marker in message for marker in retryable_markers)
    return SubmissionError(message, retryable=retryable, ambiguous=ambiguous)


class C8LedgerClient:
    """Submits only as the configured agent party and agent ledger user."""

    def __init__(self, agent_party: str, agent_user: str):
        self.agent_party = agent_party
        self.agent_user = agent_user

    def current_authorization(self, mandate_id: str) -> Authorization:
        usages = []
        for event in _active_events(
                self.agent_party, MANDATE_USAGE, self.agent_user):
            argument = _create_argument(event)
            if argument.get("mandateId") == mandate_id:
                usages.append((event, argument))
        if len(usages) != 1:
            raise AgentError(
                f"expected one current usage for {mandate_id!r}, "
                f"found {len(usages)}")

        usage_event, usage = usages[0]
        mandates = []
        for event in _active_events(
                self.agent_party, MANDATE, self.agent_user):
            if event.get("contractId") == usage.get("mandateCid"):
                mandates.append((event, _create_argument(event)))
        if len(mandates) != 1:
            raise AgentError(
                f"active mandate for {mandate_id!r} was not found uniquely")
        mandate_event, mandate = mandates[0]

        if (usage.get("owner") != mandate.get("owner")
                or usage.get("agent") != mandate.get("agent")
                or usage.get("mandateId") != mandate.get("mandateId")):
            raise AgentError("usage fields do not match the referenced mandate")
        if mandate.get("agent") != self.agent_party:
            raise AgentError("configured agent does not match the mandate")

        return Authorization(
            mandate_cid=mandate_event["contractId"],
            usage_cid=usage_event["contractId"],
            mandate_id=mandate["mandateId"],
            owner=mandate["owner"],
            agent=mandate["agent"],
            instrument_id=mandate["instrumentId"],
            expected_admin=mandate["expectedAdmin"],
            total_cap=Decimal(mandate["totalCap"]),
            allowed_counterparties=tuple(mandate["allowedCounterparties"]),
            expires_at=_parse_time(mandate["expiresAt"]),
            spent=Decimal(usage["spent"]),
            processed_references=tuple(usage["processedReferences"]),
        )

    def find_receipt(
            self, mandate_id: str, business_reference: str) -> Receipt | None:
        matches = [
            receipt for receipt in self.list_receipts(mandate_id)
            if receipt.business_reference == business_reference
        ]
        if len(matches) > 1:
            raise AgentError(
                "multiple receipts exist for one mandate/business reference")
        return matches[0] if matches else None

    def list_receipts(self, mandate_id: str) -> list[Receipt]:
        """Read the durable statement entries visible to the agent."""
        receipts = []
        for event in _active_events(
                self.agent_party, CHARGE_RECEIPT, self.agent_user):
            argument = _create_argument(event)
            if argument.get("mandateId") != mandate_id:
                continue
            receipts.append(Receipt(
                contract_id=event["contractId"],
                mandate_id=argument["mandateId"],
                merchant=argument["merchant"],
                amount=Decimal(argument["amount"]),
                business_reference=argument["businessReference"],
                owner=argument.get("owner", ""),
                agent=argument.get("agent", ""),
                instrument_id=argument.get("instrumentId", ""),
                spent_before=(Decimal(argument["spentBefore"])
                              if argument.get("spentBefore") is not None
                              else None),
                spent_after=(Decimal(argument["spentAfter"])
                             if argument.get("spentAfter") is not None
                             else None),
                charged_at=(_parse_time(argument["chargedAt"])
                            if argument.get("chargedAt") else None)))
        return sorted(
            receipts,
            key=lambda receipt: (
                receipt.charged_at.timestamp()
                if receipt.charged_at is not None else float("inf"),
                receipt.business_reference))

    def submit_charge(
            self, authorization: Authorization, request: PurchaseRequest,
            resolved: ResolvedCharge, command_id: str) -> Mapping[str, Any]:
        token_execution = {
            "transferFactoryCid": resolved.transfer_factory_cid,
            "inputHoldingCids": list(resolved.input_holding_cids),
            "choiceContext": dict(resolved.choice_context),
        }
        command = {"ExerciseCommand": {
            "templateId": MANDATE_USAGE,
            "contractId": authorization.usage_cid,
            "choice": "Charge",
            "choiceArgument": {
                "merchant": request.merchant,
                "amount": str(request.amount),
                "businessReference": request.business_reference,
                "tokenExecution": token_execution,
            },
        }}
        try:
            return c8lab.submit(
                [command], act_as=self.agent_party, sub=self.agent_user,
                disclosed=list(resolved.disclosed_contracts),
                command_id=command_id, want_transaction=True)
        except c8lab.LabError as exc:
            raise _submission_error(exc) from exc
