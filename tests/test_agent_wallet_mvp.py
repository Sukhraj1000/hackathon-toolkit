from decimal import Decimal
import io
import unittest
from unittest import mock

import agent_wallet_mvp
from canton8_agent.localnet_demo import LocalNetDemoResult, _ledger_update_id


def demo_result(**overrides):
    values = {
        "mandate_id": "mandate-1",
        "owner": "owner::1",
        "agent": "agent::1",
        "merchant": "merchant::1",
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


class MvpCommandTests(unittest.TestCase):
    def test_command_runs_one_purchase_and_prints_receipt_and_safety_check(self):
        runner = mock.Mock(return_value=demo_result())
        stdout = io.StringIO()

        with mock.patch("sys.stdout", stdout):
            status = agent_wallet_mvp.main([], runner=runner)

        self.assertEqual(0, status)
        runner.assert_called_once_with(
            amount=Decimal("0.1"), total_cap=Decimal("1.0"),
            deadline_seconds=90)
        output = stdout.getvalue()
        self.assertIn("AGENT WALLET MVP COMPLETE", output)
        self.assertIn("receipt-cid", output)
        self.assertIn("remaining        0.9 Amulet", output)
        self.assertIn("rejected: charge exceeds remaining mandate cap", output)

    def test_ledger_reference_prefers_the_committed_update_id(self):
        self.assertEqual(
            "update-42",
            _ledger_update_id({"transaction": {"updateId": "update-42"}}))
        self.assertEqual("", _ledger_update_id({"transaction": {}}))


if __name__ == "__main__":
    unittest.main()
