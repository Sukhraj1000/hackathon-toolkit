#!/usr/bin/env python3
"""Command-line interface for the reduced LocalNet agent-wallet MVP."""

import argparse
from dataclasses import asdict, dataclass
import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import shutil
import subprocess
import sys

import c8lab
from canton8_agent import (
    AgentError, C8LedgerClient, C8TokenResolver, MandateAgent,
    PurchaseRequest, ResolutionError, SubmissionError,
)
from canton8_agent.localnet_demo import LocalNetDemoResult, run_localnet_demo


DEFAULT_STATE_FILE = Path(".c8wallet-state.json")
STATE_VERSION = 1


@dataclass(frozen=True)
class WalletState:
    version: int
    mandate_id: str
    owner: str
    agent: str
    merchant: str
    instrument_id: str
    agent_user: str
    resolver_user: str

    @classmethod
    def from_demo(cls, result: LocalNetDemoResult):
        return cls(
            version=STATE_VERSION,
            mandate_id=result.mandate_id,
            owner=result.owner,
            agent=result.agent,
            merchant=result.merchant,
            instrument_id=result.instrument_id,
            agent_user=result.agent_user,
            resolver_user=result.resolver_user)

    @classmethod
    def load(cls, path: Path):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(
                f"wallet state not found at {path}; run the demo first") \
                from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not read wallet state at {path}: {exc}") \
                from exc
        expected = set(cls.__dataclass_fields__)
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("wallet state has an unexpected schema")
        if value.get("version") != STATE_VERSION:
            raise ValueError(
                f"unsupported wallet state version {value.get('version')!r}")
        if any(not isinstance(value[key], str) or not value[key]
               for key in expected - {"version"}):
            raise ValueError("wallet state contains an invalid identifier")
        return cls(**value)

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        path.chmod(0o600)


def _positive_decimal(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"{raw!r} is not a decimal") from exc
    if not value.is_finite() or value <= 0:
        raise argparse.ArgumentTypeError("value must be a positive decimal")
    return value


def _positive_float(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{raw!r} is not a number") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def _safe_text(value, maximum: int = 600) -> str:
    """Escape terminal controls in ledger and user-provided text."""
    raw = str(value)[:maximum]
    return json.dumps(raw, ensure_ascii=True)[1:-1]


def render_result(result: LocalNetDemoResult) -> str:
    ledger_reference = result.ledger_update_id or result.command_id
    return "\n".join([
        "",
        "AGENT WALLET MVP COMPLETE",
        f"mandate          {_safe_text(result.mandate_id)}",
        f"owner            {_safe_text(result.owner)}",
        f"agent            {_safe_text(result.agent)}",
        f"merchant         {_safe_text(result.merchant)}",
        f"purchase         {result.amount} {_safe_text(result.instrument_id)}",
        f"receipt          {_safe_text(result.receipt_contract_id)}",
        f"ledger reference {_safe_text(ledger_reference)}",
        f"allowance        {result.spent} / {result.total_cap} spent",
        f"remaining        {result.remaining} {_safe_text(result.instrument_id)}",
        f"safety check     rejected: {_safe_text(result.over_cap_error)}",
    ])


def render_authorization(authorization) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    status = "active" if now < authorization.expires_at else "expired"
    remaining = authorization.total_cap - authorization.spent
    merchants = "\n".join(
        f"  - {_safe_text(merchant)}"
        for merchant in authorization.allowed_counterparties)
    return "\n".join([
        "MANDATE STATUS",
        f"status            {status}",
        f"mandate           {_safe_text(authorization.mandate_id)}",
        f"owner             {_safe_text(authorization.owner)}",
        f"agent             {_safe_text(authorization.agent)}",
        f"instrument        {_safe_text(authorization.instrument_id)}",
        f"allowance         {authorization.spent} / "
        f"{authorization.total_cap} spent",
        f"remaining         {remaining}",
        f"expires           {authorization.expires_at.isoformat()}",
        "allowed merchants",
        merchants or "  (none)",
    ])


def render_purchase(outcome, authorization) -> str:
    if outcome.receipt is None:
        raise AgentError("the committed purchase receipt was not visible")
    remaining = authorization.total_cap - authorization.spent
    transaction = (
        outcome.transaction.get("transaction", {})
        if isinstance(outcome.transaction, dict) else {})
    ledger_reference = (
        transaction.get("updateId") if isinstance(transaction, dict) else None)
    return "\n".join([
        "PURCHASE COMPLETE",
        f"status            {_safe_text(outcome.status)}",
        f"merchant          {_safe_text(outcome.receipt.merchant)}",
        f"amount            {outcome.receipt.amount} "
        f"{_safe_text(authorization.instrument_id)}",
        f"reference         {_safe_text(outcome.receipt.business_reference)}",
        f"receipt           {_safe_text(outcome.receipt.contract_id)}",
        f"ledger reference  {_safe_text(ledger_reference or outcome.command_id)}",
        f"remaining         {remaining}",
    ])


def render_statement(authorization, receipts) -> str:
    remaining = authorization.total_cap - authorization.spent
    lines = [
        "LEDGER STATEMENT",
        f"mandate           {_safe_text(authorization.mandate_id)}",
        f"owner             {_safe_text(authorization.owner)}",
        f"agent             {_safe_text(authorization.agent)}",
        f"instrument        {_safe_text(authorization.instrument_id)}",
        f"spent             {authorization.spent}",
        f"remaining         {remaining}",
        f"receipts          {len(receipts)}",
    ]
    for index, receipt in enumerate(receipts, 1):
        charged_at = (
            receipt.charged_at.isoformat() if receipt.charged_at else "unknown")
        spent_range = (
            f"{receipt.spent_before} -> {receipt.spent_after}"
            if receipt.spent_before is not None
            and receipt.spent_after is not None else "unknown")
        lines.extend([
            "",
            f"[{index}] {_safe_text(charged_at)}",
            f"merchant          {_safe_text(receipt.merchant)}",
            f"amount            {receipt.amount} "
            f"{_safe_text(receipt.instrument_id or authorization.instrument_id)}",
            f"cumulative spend  {spent_range}",
            f"reference         {_safe_text(receipt.business_reference)}",
            f"receipt           {_safe_text(receipt.contract_id)}",
        ])
    return "\n".join(lines)


def run_doctor() -> int:
    checks = []
    failures = []
    if c8lab.IDP or c8lab.ACCESS_TOKEN:
        failures.append(
            "unset C8_IDP and C8_ACCESS_TOKEN; this CLI is LocalNet-only")
    else:
        checks.append("authentication   LocalNet unsafe JWT mode")

    daml = shutil.which("daml")
    if not daml:
        failures.append("Daml CLI not found; install it using SETUP.md")
    else:
        try:
            version = subprocess.run(
                [daml, "version"], check=True, capture_output=True,
                text=True, timeout=20).stdout.splitlines()[0]
            checks.append(f"Daml CLI         {_safe_text(version)}")
        except (OSError, subprocess.SubprocessError) as exc:
            failures.append(f"Daml CLI failed: {_safe_text(exc)}")

    try:
        checks.append(f"ledger offset    {c8lab.ledger_end(c8lab.ADMIN)}")
        checks.append(f"token admin      {_safe_text(c8lab.admin_party())}")
    except c8lab.LabError as exc:
        failures.append(f"LocalNet ledger unavailable: {_safe_text(exc)}")
    if c8lab.REGISTRY:
        checks.append(
            f"registry          {_safe_text(c8lab.REGISTRY + c8lab.REGISTRY_PREFIX)}")
    else:
        failures.append("C8_REGISTRY is not configured")

    print("CLI DOCTOR")
    for check in checks:
        print(f"ok    {check}")
    for failure in failures:
        print(f"error {_safe_text(failure)}")
    return 1 if failures else 0


def _state_argument(parser) -> None:
    parser.add_argument(
        "--state-file", type=Path, default=DEFAULT_STATE_FILE,
        help=f"non-secret demo state (default: {DEFAULT_STATE_FILE})")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run and inspect the LocalNet agent-wallet MVP")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="verify CLI and LocalNet prerequisites")

    demo = commands.add_parser(
        "demo", help="provision state and run the complete MVP")
    demo.add_argument(
        "--amount", type=_positive_decimal, default=Decimal("0.1"),
        help="purchase amount (default: 0.1)")
    demo.add_argument(
        "--cap", type=_positive_decimal, default=Decimal("1.0"),
        help="mandate total cap; must exceed amount (default: 1.0)")
    demo.add_argument(
        "--wait-seconds", type=_positive_float, default=90,
        help="maximum wait for LocalNet automation (default: 90)")
    _state_argument(demo)

    status = commands.add_parser("status", help="show the active mandate")
    _state_argument(status)

    buy = commands.add_parser("buy", help="charge the configured mandate")
    buy.add_argument("--amount", type=_positive_decimal, required=True)
    buy.add_argument("--reference", required=True)
    buy.add_argument(
        "--merchant",
        help="exact merchant Party ID; defaults to the demo merchant")
    _state_argument(buy)

    statement = commands.add_parser(
        "statement", help="render chronological receipts from the ledger")
    _state_argument(statement)
    return parser


def main(argv=None, *, runner=run_localnet_demo) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    commands = {"doctor", "demo", "status", "buy", "statement"}
    if not raw:
        raw = ["demo"]
    elif raw[0] not in commands and raw[0] not in {"-h", "--help"}:
        raw.insert(0, "demo")
    args = _parser().parse_args(raw)
    if args.command == "doctor":
        return run_doctor()

    try:
        if args.command == "demo":
            result = runner(
                amount=args.amount,
                total_cap=args.cap,
                deadline_seconds=args.wait_seconds)
            WalletState.from_demo(result).save(args.state_file)
            print(render_result(result))
            print(f"state             {_safe_text(args.state_file.resolve())}")
            print("next              python3 agent_wallet_mvp.py status")
            return 0

        state = WalletState.load(args.state_file)
        ledger = C8LedgerClient(state.agent, state.agent_user)
        if args.command == "status":
            print(render_authorization(
                ledger.current_authorization(state.mandate_id)))
            return 0
        if args.command == "buy":
            request = PurchaseRequest(
                merchant=args.merchant or state.merchant,
                amount=args.amount,
                business_reference=args.reference)
            wallet = MandateAgent(
                state.agent, ledger, C8TokenResolver(state.resolver_user))
            outcome = wallet.charge(state.mandate_id, request)
            current = ledger.current_authorization(state.mandate_id)
            print(render_purchase(outcome, current))
            return 0
        if args.command == "statement":
            authorization = ledger.current_authorization(state.mandate_id)
            print(render_statement(
                authorization, ledger.list_receipts(state.mandate_id)))
            return 0
    except (AgentError, ResolutionError, SubmissionError,
            c8lab.LabError, OSError, ValueError) as exc:
        print(f"ERROR: {_safe_text(exc)}", file=sys.stderr)
        return 1
    raise AssertionError("unreachable CLI command")


if __name__ == "__main__":
    raise SystemExit(main())
