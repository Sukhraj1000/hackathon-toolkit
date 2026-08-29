"""Read-only owner holding resolver for Token Standard V1 direct charges."""

import datetime
from decimal import Decimal

import c8lab

from .errors import ResolutionError
from .models import Authorization, PurchaseRequest, ResolvedCharge


def _iso(instant: datetime.datetime) -> str:
    return instant.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolver_error(exc: c8lab.LabError) -> ResolutionError:
    message = str(exc)
    retryable = any(marker in message for marker in (
        "cannot reach", "network error", "HTTP 500", "HTTP 502",
        "HTTP 503", "HTTP 504", "LOCAL_VERDICT_LOCKED_CONTRACTS",
    ))
    return ResolutionError(message, retryable=retryable)


class C8TokenResolver:
    """Run this adapter under a user with only CanReadAs(owner).

    The resulting event blobs are transaction-scoped capabilities. Do not log
    or persist them. A deployed agent should call this through a narrow service
    boundary rather than receiving the resolver credential.
    """

    def __init__(self, resolver_user: str):
        self.resolver_user = resolver_user

    def resolve(
            self, authorization: Authorization,
            request: PurchaseRequest) -> ResolvedCharge:
        try:
            visible_holdings = c8lab.holdings(
                authorization.owner, sub=self.resolver_user,
                include_disclosures=True)
        except c8lab.LabError as exc:
            raise _resolver_error(exc) from exc
        holdings = [
            holding for holding in visible_holdings
            if not holding["locked"]
            and holding["instrument"] == authorization.instrument_id
            and holding["admin"] == authorization.expected_admin
        ]
        total = sum(
            (Decimal(holding["amount"]) for holding in holdings), Decimal("0"))
        if total < request.amount:
            raise ResolutionError(
                f"owner has {total} spendable {authorization.instrument_id}, "
                f"needs {request.amount}")

        now = datetime.datetime.now(datetime.timezone.utc)
        transfer = {
            "sender": authorization.owner,
            "receiver": request.merchant,
            "amount": str(request.amount),
            "instrumentId": {
                "admin": authorization.expected_admin,
                "id": authorization.instrument_id,
            },
            "requestedAt": _iso(now),
            "executeBefore": _iso(authorization.expires_at),
            "inputHoldingCids": [holding["contractId"] for holding in holdings],
            "meta": {"values": {}},
        }
        factory_args = {
            "expectedAdmin": authorization.expected_admin,
            "transfer": transfer,
            "extraArgs": {
                "context": {"values": {}},
                "meta": {"values": {}},
            },
        }
        try:
            factory = c8lab.registry(
                "/registry/transfer-instruction/v1/transfer-factory",
                {"choiceArguments": factory_args})
        except c8lab.LabError as exc:
            raise _resolver_error(exc) from exc
        factory_id = factory.get("factoryId")
        if not factory_id:
            raise ResolutionError("registry response omitted transfer factory ID")
        choice_context = factory.get("choiceContext", {})
        context_data = choice_context.get("choiceContextData", {})

        disclosures = list(choice_context.get("disclosedContracts", []))
        disclosures.extend({
            field: holding[field]
            for field in (
                "templateId", "contractId", "createdEventBlob",
                "synchronizerId")
        } for holding in holdings)
        unique_disclosures = []
        seen_contracts = set()
        for disclosure in disclosures:
            contract_id = disclosure.get("contractId")
            if contract_id and contract_id not in seen_contracts:
                seen_contracts.add(contract_id)
                unique_disclosures.append(disclosure)

        return ResolvedCharge(
            transfer_factory_cid=factory_id,
            input_holding_cids=tuple(transfer["inputHoldingCids"]),
            choice_context=context_data,
            disclosed_contracts=tuple(unique_disclosures),
            transfer_kind=factory.get("transferKind", ""),
        )
