import datetime
from decimal import Decimal
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import agent_wallet_mvp
from canton8_agent import (
    Authorization, ChargeOutcome, MissionResult, Offer, PurchaseRequest, Receipt,
)
from canton8_agent.localnet_demo import LocalNetDemoResult, _ledger_update_id
from canton8_agent import localnet_demo
from canton8_agent.proof import ProofResult, ProofStep


UTC = datetime.timezone.utc


def demo_result(**overrides):
    values = {
        "mandate_id": "mandate-1",
        "owner": "owner::1",
        "agent": "agent::1",
        "merchant": "merchant::1",
        "owner_user": "owner-user",
        "agent_user": "agent-user",
        "merchant_user": "merchant-user",
        "resolver_user": "resolver-user",
        "instrument_id": "Amulet",
        "amount": Decimal("0.1"),
        "total_cap": Decimal("1.0"),
        "spent": Decimal("0.1"),
        "remaining": Decimal("0.9"),
        "receipt_contract_id": "receipt-cid",
        "command_id": "command-id",
        "ledger_update_id": "update-id",
        "over_cap_error": "charge exceeds remaining mandate cap",
    }
    values.update(overrides)
    return LocalNetDemoResult(**values)


def wallet_state():
    return agent_wallet_mvp.WalletState(
        version=2,
        mandate_id="mandate-1",
        owner="owner::1",
        agent="agent::1",
        merchant="merchant::1",
        instrument_id="Amulet",
        owner_user="owner-user",
        agent_user="agent-user",
        merchant_user="merchant-user",
        resolver_user="resolver-user")


def authorization(**overrides):
    values = {
        "mandate_cid": "mandate-cid",
        "usage_cid": "usage-cid",
        "mandate_id": "mandate-1",
        "owner": "owner::1",
        "agent": "agent::1",
        "instrument_id": "Amulet",
        "expected_admin": "DSO::1",
        "total_cap": Decimal("1.0"),
        "allowed_counterparties": ("merchant::1",),
        "expires_at": datetime.datetime.now(UTC) + datetime.timedelta(hours=1),
        "spent": Decimal("0.1"),
        "processed_references": ("first-order",),
    }
    values.update(overrides)
    return Authorization(**values)


class MvpCommandTests(unittest.TestCase):
    def test_version_one_state_is_upgraded_without_credentials(self):
        legacy = {
            "version": 1,
            "mandate_id": "mandate-1",
            "owner": "owner-user::1",
            "agent": "agent::1",
            "merchant": "merchant-user::1",
            "instrument_id": "Amulet",
            "agent_user": "agent-user",
            "resolver_user": "resolver-user",
        }
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "wallet.json"
            state_path.write_text(json.dumps(legacy), encoding="utf-8")
            state = agent_wallet_mvp.WalletState.load(state_path)

        self.assertEqual(2, state.version)
        self.assertEqual("owner-user", state.owner_user)
        self.assertEqual("merchant-user", state.merchant_user)

    def test_demo_returns_cli_identity_state_after_purchase(self):
        ledger = mock.Mock()
        ledger.current_authorization.return_value = authorization()
        ledger.submit_charge.side_effect = agent_wallet_mvp.SubmissionError(
            "total cap exceeded", retryable=False)
        resolver = mock.Mock()
        resolver.resolve.return_value = mock.Mock(transfer_kind="direct")
        wallet = mock.Mock()
        wallet.charge.return_value = ChargeOutcome(
            status="committed", command_id="command-1",
            receipt=Receipt(
                contract_id="receipt-1", mandate_id="mvp-mandate-run123",
                merchant="merchant::1", amount=Decimal("0.1"),
                business_reference="mvp-order-run123"))
        fixed_uuid = mock.Mock(hex="run123")
        with mock.patch.object(localnet_demo, "_upload_mandate_dar"), \
             mock.patch.object(
                 localnet_demo.uuid, "uuid4", return_value=fixed_uuid), \
             mock.patch.object(
                 localnet_demo.c8lab, "allocate_party",
                 side_effect=["owner::1", "agent::1", "merchant::1"]), \
             mock.patch.object(localnet_demo, "_create_user"), \
             mock.patch.object(
                 localnet_demo.c8lab, "find_party", return_value="provider::1"), \
             mock.patch.object(
                 localnet_demo.c8lab, "create_preapproval_proposal"), \
             mock.patch.object(localnet_demo, "_fund_owner"), \
             mock.patch.object(
                 localnet_demo.c8lab, "admin_party", return_value="DSO::1"), \
             mock.patch.object(localnet_demo.c8lab, "submit"), \
             mock.patch.object(
                 localnet_demo, "_only_contract_id", return_value="proposal"), \
             mock.patch.object(
                 localnet_demo, "C8LedgerClient", return_value=ledger), \
             mock.patch.object(
                 localnet_demo, "C8TokenResolver", return_value=resolver), \
             mock.patch.object(
                 localnet_demo, "MandateAgent", return_value=wallet), \
             mock.patch.object(localnet_demo, "_wait_for_direct"):
            result = localnet_demo.run_localnet_demo(
                progress=mock.Mock(), sleeper=lambda _: None)

        self.assertEqual("mvp-agent-run123", result.agent_user)
        self.assertEqual("mvp-owner-run123", result.owner_user)
        self.assertEqual("mvp-merchant-run123", result.merchant_user)
        self.assertEqual("mvp-resolver-run123", result.resolver_user)
        self.assertEqual("agent::1", result.agent)
        first_request = wallet.charge.call_args_list[0].args[1]
        self.assertEqual("merchant::1", first_request.merchant)
        self.assertEqual(Decimal("0.1"), first_request.amount)
        self.assertEqual(1, wallet.charge.call_count)
        resolver.resolve.assert_called_once()
        ledger.submit_charge.assert_called_once()
        submitted_request = ledger.submit_charge.call_args.args[1]
        self.assertEqual(Decimal("0.91"), submitted_request.amount)

    def test_demo_funding_retries_an_inactive_provider_holding(self):
        with mock.patch.object(
                localnet_demo.c8lab, "transfer", side_effect=[
                    localnet_demo.c8lab.LabError(
                        "LOCAL_VERDICT_INACTIVE_CONTRACTS"),
                    {"transferKind": "direct"},
                ]) as transfer, \
             mock.patch.object(
                 localnet_demo.c8lab, "accept_transfer") as accept:
            localnet_demo._fund_owner(
                "provider::1", "owner::1", Decimal("1"), "owner-user",
                deadline_seconds=10, sleeper=lambda _: None)

        self.assertEqual(2, transfer.call_count)
        accept.assert_not_called()

    def test_demo_runs_purchase_prints_receipt_and_saves_non_secret_state(self):
        runner = mock.Mock(return_value=demo_result())
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "wallet.json"
            with mock.patch("sys.stdout", stdout):
                status = agent_wallet_mvp.main(
                    ["demo", "--state-file", str(state_path)], runner=runner)

            actual_state = agent_wallet_mvp.WalletState.load(state_path)
            self.assertEqual("mandate-1", actual_state.mandate_id)
            self.assertEqual("agent-user", actual_state.agent_user)
            self.assertNotIn("token", state_path.read_text(encoding="utf-8"))
            self.assertEqual(0o600, state_path.stat().st_mode & 0o777)

        self.assertEqual(0, status)
        runner.assert_called_once_with(
            amount=Decimal("0.1"), total_cap=Decimal("1.0"),
            deadline_seconds=90)
        output = stdout.getvalue()
        self.assertIn("AGENT WALLET MVP COMPLETE", output)
        self.assertIn("receipt-cid", output)
        self.assertIn("remaining        0.9 Amulet", output)
        self.assertIn(
            "on-ledger rejected: charge exceeds remaining mandate cap", output)

    def test_status_uses_only_the_state_bound_agent_identity(self):
        ledger = mock.Mock()
        ledger.current_authorization.return_value = authorization()
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "wallet.json"
            wallet_state().save(state_path)
            with mock.patch(
                    "agent_wallet_mvp.C8LedgerClient",
                    return_value=ledger) as client, \
                 mock.patch("sys.stdout", stdout):
                status = agent_wallet_mvp.main([
                    "status", "--state-file", str(state_path)])

        self.assertEqual(0, status)
        client.assert_called_once_with("agent::1", "agent-user")
        ledger.current_authorization.assert_called_once_with("mandate-1")
        self.assertIn("MANDATE STATUS", stdout.getvalue())
        self.assertIn("remaining         0.9", stdout.getvalue())

    def test_buy_uses_configured_merchant_and_resolver(self):
        ledger = mock.Mock()
        ledger.current_authorization.return_value = authorization(
            spent=Decimal("0.15"))
        receipt = Receipt(
            contract_id="receipt-2", mandate_id="mandate-1",
            merchant="merchant::1", amount=Decimal("0.05"),
            business_reference="second-order")
        wallet = mock.Mock()
        wallet.charge.return_value = ChargeOutcome(
            status="committed", command_id="command-2", receipt=receipt,
            transaction={"transaction": {"updateId": "update-2"}})
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "wallet.json"
            wallet_state().save(state_path)
            with mock.patch(
                    "agent_wallet_mvp.C8LedgerClient", return_value=ledger), \
                 mock.patch(
                     "agent_wallet_mvp.C8TokenResolver",
                     return_value="resolver") as resolver, \
                 mock.patch(
                     "agent_wallet_mvp.MandateAgent",
                     return_value=wallet) as agent, \
                 mock.patch("sys.stdout", stdout):
                status = agent_wallet_mvp.main([
                    "buy", "--amount", "0.05", "--reference", "second-order",
                    "--state-file", str(state_path)])

        self.assertEqual(0, status)
        resolver.assert_called_once_with("resolver-user")
        agent.assert_called_once_with("agent::1", ledger, "resolver")
        wallet.charge.assert_called_once_with(
            "mandate-1",
            PurchaseRequest("merchant::1", Decimal("0.05"), "second-order"))
        self.assertIn("PURCHASE COMPLETE", stdout.getvalue())
        self.assertIn("remaining         0.85", stdout.getvalue())

    def test_statement_escapes_controls_and_uses_ledger_receipts(self):
        ledger = mock.Mock()
        ledger.current_authorization.return_value = authorization(revoked=True)
        ledger.list_receipts.return_value = [Receipt(
            contract_id="receipt-1", mandate_id="mandate-1",
            mandate_cid="mandate-cid",
            owner="owner::1", agent="agent::1", merchant="merchant::1",
            instrument_id="Amulet", amount=Decimal("0.1"),
            spent_before=Decimal("0"), spent_after=Decimal("0.1"),
            charged_at=datetime.datetime(2026, 8, 29, tzinfo=UTC),
            business_reference="first\x1b[2Jorder")]
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "wallet.json"
            wallet_state().save(state_path)
            with mock.patch(
                    "agent_wallet_mvp.C8LedgerClient", return_value=ledger), \
                 mock.patch("sys.stdout", stdout):
                status = agent_wallet_mvp.main([
                    "statement", "--state-file", str(state_path)])

        self.assertEqual(0, status)
        ledger.list_receipts.assert_called_once_with("mandate-1")
        output = stdout.getvalue()
        self.assertIn("LEDGER STATEMENT", output)
        self.assertIn("status            revoked", output)
        self.assertIn("authorization     mandate-cid", output)
        self.assertIn("authorized by     mandate-cid", output)
        self.assertIn("first\\u001b[2Jorder", output)
        self.assertNotIn("\x1b", output)

    def test_ledger_reference_prefers_the_committed_update_id(self):
        self.assertEqual(
            "update-42",
            _ledger_update_id({"transaction": {"updateId": "update-42"}}))
        self.assertEqual("", _ledger_update_id({"transaction": {}}))

    def test_mission_command_emits_structured_agent_decision(self):
        current = authorization(spent=Decimal("0.15"))
        offer = Offer(
            "merchant::1", Decimal("0.05"), "mission-order",
            {"id": "weather", "title": "Weather API",
             "description": "Forecast data"})
        receipt = Receipt(
            "receipt-mission", "mandate-1", "merchant::1", Decimal("0.05"),
            "mission-order", instrument_id="Amulet")
        result = MissionResult(
            mission="Buy forecast data", planner="test-planner", model="test-model",
            selected_offer_id="weather", rationale="Best eligible data",
            guardrail="selected offer satisfies the current mandate",
            offers=(offer,),
            request=PurchaseRequest(
                "merchant::1", Decimal("0.05"), "mission-order"),
            outcome=ChargeOutcome(
                "committed", "command", receipt=receipt),
            authorization=current)
        mission_runner = mock.Mock(return_value=result)
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "wallet.json"
            wallet_state().save(state_path)
            with mock.patch("sys.stdout", stdout):
                status = agent_wallet_mvp.main([
                    "mission", "--goal", "Buy forecast data", "--json",
                    "--state-file", str(state_path),
                ], mission_runner=mission_runner)

        self.assertEqual(0, status)
        mission_runner.assert_called_once_with(
            mock.ANY, "Buy forecast data")
        payload = json.loads(stdout.getvalue())
        self.assertEqual("mission", payload["kind"])
        self.assertEqual("weather", payload["decision"]["offerId"])
        self.assertEqual("receipt-mission", payload["receipt"]["contractId"])

    def test_proof_command_emits_structured_attack_timeline(self):
        proof = ProofResult(
            mandate_id="proof-mandate", owner="owner::1", agent="agent::1",
            merchant="merchant::1", instrument_id="Amulet",
            legitimate_receipt="receipt-1", spent=Decimal("0.05"),
            total_cap=Decimal("0.20"), receipt_count=1, revoked=True,
            steps=(ProofStep(
                "over-cap", "Over-cap bypass blocked", "rejected",
                "total cap exceeded", "Daml totalCap assertion"),))
        proof_runner = mock.Mock(return_value=proof)
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", io.StringIO()):
            status = agent_wallet_mvp.main(
                ["proof", "--json"], proof_runner=proof_runner)

        self.assertEqual(0, status)
        proof_runner.assert_called_once()
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["revoked"])
        self.assertEqual("rejected", payload["steps"][0]["status"])


if __name__ == "__main__":
    unittest.main()
