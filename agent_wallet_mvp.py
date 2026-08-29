#!/usr/bin/env python3
"""Run the reduced, one-command LocalNet agent-wallet MVP."""

import argparse
from decimal import Decimal, InvalidOperation
import sys

import c8lab
from canton8_agent import AgentError, ResolutionError, SubmissionError
from canton8_agent.localnet_demo import LocalNetDemoResult, run_localnet_demo


def _positive_decimal(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"{raw!r} is not a decimal") from exc
    if not value.is_finite() or value <= 0:
        raise argparse.ArgumentTypeError("value must be a positive decimal")
    return value


def render_result(result: LocalNetDemoResult) -> str:
    ledger_reference = result.ledger_update_id or result.command_id
    return "\n".join([
        "",
        "AGENT WALLET MVP COMPLETE",
        f"mandate          {result.mandate_id}",
        f"owner            {result.owner}",
        f"agent            {result.agent}",
        f"merchant         {result.merchant}",
        f"purchase         {result.amount} {result.instrument_id}",
        f"receipt          {result.receipt_contract_id}",
        f"ledger reference {ledger_reference}",
        f"allowance        {result.spent} / {result.total_cap} spent",
        f"remaining        {result.remaining} {result.instrument_id}",
        f"safety check     rejected: {result.over_cap_error}",
    ])


def main(argv=None, *, runner=run_localnet_demo) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Provision a fresh LocalNet mandate, make one atomic Canton Coin "
            "purchase, print its receipt, and reject one over-cap request."))
    parser.add_argument(
        "--amount", type=_positive_decimal, default=Decimal("0.1"),
        help="purchase amount (default: 0.1)")
    parser.add_argument(
        "--cap", type=_positive_decimal, default=Decimal("1.0"),
        help="mandate total cap; must exceed amount (default: 1.0)")
    parser.add_argument(
        "--wait-seconds", type=float, default=90,
        help="maximum wait for LocalNet automation (default: 90)")
    args = parser.parse_args(argv)
    try:
        result = runner(
            amount=args.amount,
            total_cap=args.cap,
            deadline_seconds=args.wait_seconds)
    except (AgentError, ResolutionError, SubmissionError,
            c8lab.LabError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(render_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
