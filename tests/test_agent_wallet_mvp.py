import datetime
from decimal import Decimal
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import agent_wallet_mvp
from canton8_agent import Authorization, ChargeOutcome, PurchaseRequest, Receipt
from canton8_agent.localnet_demo import LocalNetDemoResult, _ledger_update_id
from canton8_agent import localnet_demo


UTC = datetime.timezone.utc


def demo_result(**overrides):
    values = {
        "mandate_id": "mandate-1",
        "owner": "owner::1",
        "agent": "agent::1",
        "merchant": "merchant::1",
        "agent_user": "agent-user",
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
        version=1,
        mandate_id="mandate-1",
        owner="owner::1",
        agent="agent::1",
        merchant="merchant::1",
        instrument_id="Amulet",
        agent_user="agent-user",
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
    def test_demo_returns_cli_identity_state_after_purchase(self):
        ledger = mock.Mock()
        ledger.current_authorization.return_value = authorization()
        wallet = mock.Mock()
        wallet.charge.side_effect = [
            ChargeOutcome(
                status="committed", command_id="command-1",
                receipt=Receipt(
                    contract_id="receipt-1", mandate_id="mvp-mandate-run123",
                    merchant="merchant::1", amount=Decimal("0.1"),
                    business_reference="mvp-order-run123")),
            agent_wallet_mvp.AgentError(
                "charge exceeds remaining mandate cap"),
        ]
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
             mock.patch.object(localnet_demo, "C8TokenResolver"), \
             mock.patch.object(
                 localnet_demo, "MandateAgent", return_value=wallet), \
             mock.patch.object(localnet_demo, "_wait_for_direct"):
            result = localnet_demo.run_localnet_demo(
                progress=mock.Mock(), sleeper=lambda _: None)

        self.assertEqual("mvp-agent-run123", result.agent_user)
        self.assertEqual("mvp-resolver-run123", result.resolver_user)
        self.assertEqual("agent::1", result.agent)
        first_request = wallet.charge.call_args_list[0].args[1]
        self.assertEqual("merchant::1", first_request.merchant)
        self.assertEqual(Decimal("0.1"), first_request.amount)

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
        self.assertIn("rejected: charge exceeds remaining mandate cap", output)

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
        ledger.current_authorization.return_value = authorization()
        ledger.list_receipts.return_value = [Receipt(
            contract_id="receipt-1", mandate_id="mandate-1",
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
        self.assertIn("first\\u001b[2Jorder", output)
        self.assertNotIn("\x1b", output)

    def test_ledger_reference_prefers_the_committed_update_id(self):
        self.assertEqual(
            "update-42",
            _ledger_update_id({"transaction": {"updateId": "update-42"}}))
        self.assertEqual("", _ledger_update_id({"transaction": {}}))


if __name__ == "__main__":
    unittest.main()
