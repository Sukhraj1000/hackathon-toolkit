import datetime
from decimal import Decimal
import unittest
from unittest import mock

import c8lab
from canton8_agent import (
    AgentError, Authorization, C8LedgerClient, C8TokenResolver, FixedApproval,
    LowestPriceDecision, MandateAgent, Offer, PurchaseRequest, Receipt,
    ResolvedCharge, ResolutionError, SubmissionError, command_id_for,
)
from canton8_agent import ledger as ledger_module


UTC = datetime.timezone.utc


def authorization(**overrides):
    values = {
        "mandate_cid": "mandate-cid",
        "usage_cid": "usage-cid-0",
        "mandate_id": "mandate-1",
        "owner": "owner::1",
        "agent": "agent::1",
        "instrument_id": "Amulet",
        "expected_admin": "DSO::1",
        "total_cap": Decimal("100"),
        "allowed_counterparties": ("merchant::1",),
        "expires_at": datetime.datetime(2030, 1, 1, tzinfo=UTC),
        "spent": Decimal("10"),
        "processed_references": (),
    }
    values.update(overrides)
    return Authorization(**values)


def purchase(**overrides):
    values = {
        "merchant": "merchant::1",
        "amount": Decimal("12.5"),
        "business_reference": "order-42",
    }
    values.update(overrides)
    return PurchaseRequest(**values)


def resolution(**overrides):
    values = {
        "transfer_factory_cid": "factory-cid",
        "input_holding_cids": ("holding-cid",),
        "choice_context": {"values": {"registry": "context"}},
        "disclosed_contracts": ({
            "templateId": "pkg:Mod:Holding",
            "contractId": "holding-cid",
            "createdEventBlob": "blob",
            "synchronizerId": "sync",
        },),
        "transfer_kind": "direct",
    }
    values.update(overrides)
    return ResolvedCharge(**values)


class FakeLedger:
    def __init__(self, authorizations=None, submissions=None):
        self.authorizations = list(authorizations or [authorization()])
        self.submissions = list(submissions or [{}])
        self.receipts = {}
        self.authorization_calls = 0
        self.submit_calls = []

    def current_authorization(self, mandate_id):
        index = min(self.authorization_calls, len(self.authorizations) - 1)
        self.authorization_calls += 1
        return self.authorizations[index]

    def find_receipt(self, mandate_id, business_reference):
        return self.receipts.get((mandate_id, business_reference))

    def submit_charge(self, auth, request, resolved, command_id):
        self.submit_calls.append((auth, request, resolved, command_id))
        result = self.submissions.pop(0)
        if callable(result):
            return result(self, auth, request, resolved, command_id)
        if isinstance(result, Exception):
            raise result
        self.receipts[(auth.mandate_id, request.business_reference)] = Receipt(
            contract_id="receipt-cid",
            mandate_id=auth.mandate_id,
            merchant=request.merchant,
            amount=request.amount,
            business_reference=request.business_reference)
        return result


class FakeResolver:
    def __init__(self, resolved=None):
        self.resolved = resolved or resolution()
        self.calls = []

    def resolve(self, auth, request):
        self.calls.append((auth, request))
        if isinstance(self.resolved, Exception):
            raise self.resolved
        return self.resolved


class MandateAgentTests(unittest.TestCase):
    def agent(self, ledger, resolver, **kwargs):
        return MandateAgent(
            "agent::1", ledger, resolver,
            now=lambda: datetime.datetime(2029, 1, 1, tzinfo=UTC),
            sleeper=lambda _: None,
            **kwargs)

    def test_success_uses_actual_mandate_fields_and_stable_command_id(self):
        ledger = FakeLedger()
        resolver = FakeResolver()
        request = purchase()

        outcome = self.agent(ledger, resolver).charge("mandate-1", request)

        self.assertEqual("committed", outcome.status)
        self.assertEqual(
            command_id_for("mandate-1", "order-42"), outcome.command_id)
        self.assertEqual(1, len(ledger.submit_calls))
        self.assertEqual("usage-cid-0", ledger.submit_calls[0][0].usage_cid)
        self.assertEqual("receipt-cid", outcome.receipt.contract_id)

    def test_local_policy_rejection_never_calls_resolver_or_ledger_submit(self):
        ledger = FakeLedger()
        resolver = FakeResolver()
        with self.assertRaisesRegex(AgentError, "merchant"):
            self.agent(ledger, resolver).charge(
                "mandate-1", purchase(merchant="blocked::1"))
        self.assertEqual([], resolver.calls)
        self.assertEqual([], ledger.submit_calls)

    def test_over_cap_purchase_is_rejected_before_resolution_or_submission(self):
        ledger = FakeLedger([authorization(
            total_cap=Decimal("20"), spent=Decimal("10"))])
        resolver = FakeResolver()

        with self.assertRaisesRegex(AgentError, "remaining mandate cap"):
            self.agent(ledger, resolver).charge(
                "mandate-1", purchase(amount=Decimal("10.01")))

        self.assertEqual([], resolver.calls)
        self.assertEqual([], ledger.submit_calls)

    def test_non_direct_resolution_is_rejected_before_submission(self):
        ledger = FakeLedger()
        resolver = FakeResolver(resolution(transfer_kind="offer"))
        with self.assertRaisesRegex(AgentError, "preapproved"):
            self.agent(ledger, resolver).charge("mandate-1", purchase())
        self.assertEqual([], ledger.submit_calls)

    def test_retry_refreshes_usage_and_reuses_command_id(self):
        first = authorization(usage_cid="usage-cid-0")
        second = authorization(usage_cid="usage-cid-1")
        ledger = FakeLedger(
            [first, second],
            [SubmissionError("locked", retryable=True), {"tx": "ok"}])
        resolver = FakeResolver()

        outcome = self.agent(ledger, resolver).charge(
            "mandate-1", purchase(), max_attempts=2)

        self.assertEqual("committed", outcome.status)
        self.assertEqual(2, len(ledger.submit_calls))
        self.assertEqual(
            ["usage-cid-0", "usage-cid-1"],
            [call[0].usage_cid for call in ledger.submit_calls])
        self.assertEqual(
            1, len({call[3] for call in ledger.submit_calls}),
            "every retry must reuse the same command id")

    def test_retryable_resolver_failure_refreshes_before_submission(self):
        class RetryResolver:
            def __init__(self):
                self.calls = 0

            def resolve(self, auth, request):
                self.calls += 1
                if self.calls == 1:
                    raise ResolutionError("registry unavailable", retryable=True)
                return resolution()

        ledger = FakeLedger([
            authorization(usage_cid="usage-cid-0"),
            authorization(usage_cid="usage-cid-1"),
        ])
        resolver = RetryResolver()
        outcome = self.agent(ledger, resolver).charge(
            "mandate-1", purchase(), max_attempts=2)

        self.assertEqual("committed", outcome.status)
        self.assertEqual(2, resolver.calls)
        self.assertEqual("usage-cid-1", ledger.submit_calls[0][0].usage_cid)

    def test_ambiguous_result_reconciles_receipt_before_retry(self):
        request = purchase()

        def committed_then_disconnected(
                ledger, auth, request, resolved, command_id):
            ledger.receipts[(auth.mandate_id, request.business_reference)] = Receipt(
                contract_id="committed-receipt",
                mandate_id=auth.mandate_id,
                merchant=request.merchant,
                amount=request.amount,
                business_reference=request.business_reference)
            raise SubmissionError(
                "network error after commit", retryable=True, ambiguous=True)

        ledger = FakeLedger(submissions=[committed_then_disconnected])
        outcome = self.agent(ledger, FakeResolver()).charge(
            "mandate-1", request, max_attempts=3)

        self.assertEqual("already_committed", outcome.status)
        self.assertEqual("committed-receipt", outcome.receipt.contract_id)
        self.assertEqual(1, len(ledger.submit_calls))

    def test_existing_reference_must_match_original_charge(self):
        ledger = FakeLedger()
        ledger.receipts[("mandate-1", "order-42")] = Receipt(
            contract_id="receipt-cid", mandate_id="mandate-1",
            merchant="different::1", amount=Decimal("12.5"),
            business_reference="order-42")
        with self.assertRaisesRegex(AgentError, "different committed"):
            self.agent(ledger, FakeResolver()).charge(
                "mandate-1", purchase())
        self.assertEqual([], ledger.submit_calls)

    def test_terminal_submission_error_is_not_retried(self):
        ledger = FakeLedger(submissions=[
            SubmissionError("authorization denied", retryable=False)])
        with self.assertRaises(SubmissionError):
            self.agent(ledger, FakeResolver()).charge(
                "mandate-1", purchase(), max_attempts=3)
        self.assertEqual(1, len(ledger.submit_calls))

    def test_approval_is_required_once_above_threshold(self):
        rejected = self.agent(
            FakeLedger(), FakeResolver(), approval=FixedApproval(False),
            approval_threshold=Decimal("10"))
        with self.assertRaisesRegex(AgentError, "owner rejected"):
            rejected.charge("mandate-1", purchase())

        ledger = FakeLedger()
        approved = self.agent(
            ledger, FakeResolver(), approval=FixedApproval(True),
            approval_threshold=Decimal("10"))
        self.assertEqual(
            "committed", approved.charge("mandate-1", purchase()).status)


class DecisionTests(unittest.TestCase):
    def test_selection_uses_allowed_counterparties_and_remaining_total_cap(self):
        offers = [
            Offer("blocked::1", Decimal("1"), "blocked"),
            Offer("merchant::1", Decimal("95"), "over-remaining"),
            Offer("merchant::1", Decimal("20"), "valid-20"),
            Offer("merchant::1", Decimal("12"), "valid-12"),
        ]
        selected = LowestPriceDecision().choose(offers, authorization())
        self.assertEqual(
            PurchaseRequest("merchant::1", Decimal("12"), "valid-12"),
            selected)


class C8LedgerClientTests(unittest.TestCase):
    def test_charge_command_acts_only_as_agent_and_matches_daml_shape(self):
        client = C8LedgerClient("agent::1", "agent-user")
        with mock.patch.object(
                c8lab, "submit", return_value={"transaction": {}}) as submit:
            client.submit_charge(
                authorization(), purchase(), resolution(), "stable-command")

        args, kwargs = submit.call_args
        command = args[0][0]["ExerciseCommand"]
        self.assertEqual("agent::1", kwargs["act_as"])
        self.assertEqual("agent-user", kwargs["sub"])
        self.assertEqual("Charge", command["choice"])
        self.assertEqual("usage-cid-0", command["contractId"])
        self.assertEqual({
            "merchant": "merchant::1",
            "amount": "12.5",
            "businessReference": "order-42",
            "tokenExecution": {
                "transferFactoryCid": "factory-cid",
                "inputHoldingCids": ["holding-cid"],
                "choiceContext": {"values": {"registry": "context"}},
            },
        }, command["choiceArgument"])
        self.assertEqual("stable-command", kwargs["command_id"])

    def test_network_failure_is_ambiguous_and_retryable(self):
        client = C8LedgerClient("agent::1", "agent-user")
        with mock.patch.object(
                c8lab, "submit",
                side_effect=c8lab.LabError("network error after submission")):
            with self.assertRaises(SubmissionError) as raised:
                client.submit_charge(
                    authorization(), purchase(), resolution(), "command")
        self.assertTrue(raised.exception.retryable)
        self.assertTrue(raised.exception.ambiguous)

    def test_authorization_adapter_reads_current_contract_field_names(self):
        usage_event = {"contractId": "usage-cid", "createArgument": {
            "mandateCid": "mandate-cid", "mandateId": "mandate-1",
            "owner": "owner::1", "agent": "agent::1", "spent": "10.0",
            "processedReferences": ["old-order"],
        }}
        mandate_event = {"contractId": "mandate-cid", "createArgument": {
            "mandateId": "mandate-1", "owner": "owner::1",
            "agent": "agent::1", "instrumentId": "Amulet",
            "expectedAdmin": "DSO::1", "totalCap": "100.0",
            "allowedCounterparties": ["merchant::1"],
            "expiresAt": "2030-01-01T00:00:00Z",
        }}

        def active_events(party, template_id, user_id):
            if template_id == ledger_module.MANDATE_USAGE:
                return [usage_event]
            if template_id == ledger_module.MANDATE:
                return [mandate_event]
            return []

        with mock.patch.object(
                ledger_module, "_active_events", side_effect=active_events):
            actual = C8LedgerClient(
                "agent::1", "agent-user").current_authorization("mandate-1")

        self.assertEqual("usage-cid", actual.usage_cid)
        self.assertEqual(Decimal("100.0"), actual.total_cap)
        self.assertEqual(("merchant::1",), actual.allowed_counterparties)
        self.assertEqual(("old-order",), actual.processed_references)


class C8TokenResolverTests(unittest.TestCase):
    def test_resolver_derives_registry_request_and_returns_disclosures(self):
        holdings = [{
            "contractId": "holding-cid",
            "amount": "25.0",
            "instrument": "Amulet",
            "admin": "DSO::1",
            "locked": False,
            "templateId": "pkg:Token:Holding",
            "createdEventBlob": "holding-blob",
            "synchronizerId": "sync",
        }]
        factory = {
            "factoryId": "factory-cid",
            "transferKind": "direct",
            "choiceContext": {
                "choiceContextData": {"values": {"rules": "cid"}},
                "disclosedContracts": [{
                    "templateId": "pkg:Rules:Rules",
                    "contractId": "rules-cid",
                    "createdEventBlob": "rules-blob",
                    "synchronizerId": "sync",
                }],
            },
        }
        with mock.patch.object(
                c8lab, "holdings", return_value=holdings) as get_holdings, \
             mock.patch.object(
                 c8lab, "registry", return_value=factory) as registry:
            resolved = C8TokenResolver("resolver-user").resolve(
                authorization(), purchase())

        get_holdings.assert_called_once_with(
            "owner::1", sub="resolver-user", include_disclosures=True)
        request = registry.call_args.args[1]["choiceArguments"]
        transfer = request["transfer"]
        self.assertEqual("owner::1", transfer["sender"])
        self.assertEqual("merchant::1", transfer["receiver"])
        self.assertEqual("12.5", transfer["amount"])
        self.assertEqual(
            {"admin": "DSO::1", "id": "Amulet"},
            transfer["instrumentId"])
        self.assertEqual(("holding-cid",), resolved.input_holding_cids)
        self.assertEqual("direct", resolved.transfer_kind)
        self.assertEqual(
            {"rules-cid", "holding-cid"},
            {item["contractId"] for item in resolved.disclosed_contracts})


if __name__ == "__main__":
    unittest.main()
