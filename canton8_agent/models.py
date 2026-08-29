"""Domain values shared by the agent, ledger adapter, and token resolver."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping


@dataclass(frozen=True)
class Authorization:
    mandate_cid: str
    usage_cid: str
    mandate_id: str
    owner: str
    agent: str
    instrument_id: str
    expected_admin: str
    total_cap: Decimal
    allowed_counterparties: tuple[str, ...]
    expires_at: datetime
    spent: Decimal
    processed_references: tuple[str, ...]


@dataclass(frozen=True)
class PurchaseRequest:
    merchant: str
    amount: Decimal
    business_reference: str


@dataclass(frozen=True)
class ResolvedCharge:
    transfer_factory_cid: str
    input_holding_cids: tuple[str, ...]
    choice_context: Mapping[str, Any]
    disclosed_contracts: tuple[Mapping[str, Any], ...]
    transfer_kind: str


@dataclass(frozen=True)
class Receipt:
    contract_id: str
    mandate_id: str
    merchant: str
    amount: Decimal
    business_reference: str


@dataclass(frozen=True)
class ChargeOutcome:
    status: str
    command_id: str
    receipt: Receipt | None = None
    transaction: Mapping[str, Any] = field(default_factory=dict)
