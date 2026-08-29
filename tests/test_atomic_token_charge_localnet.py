"""Real Splice LocalNet proof for MandateUsage.Charge.

The integration case is opt-in because it allocates parties, uploads a DAR,
and moves real LocalNet Canton Coin. Unit discovery still covers the disclosure
resolver without requiring a running ledger.
"""

import datetime
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock
import urllib.parse

import c8lab
from canton8_agent import (
    C8LedgerClient, C8TokenResolver, MandateAgent, PurchaseRequest,
)


ROOT = Path(__file__).resolve().parents[1]
MANDATE_PROPOSAL = "#c8-agent-wallet:Mandate:MandateProposal"
MANDATE_USAGE = "#c8-agent-wallet:Mandate:MandateUsage"
CHARGE_RECEIPT = "#c8-agent-wallet:Mandate:ChargeReceipt"


def _right(kind, party):
    return {"kind": {kind: {"value": {"party": party}}}}


def _create_user(user_id, primary_party, rights):
    c8lab.call(
        "/v2/users",
        {"user": {"id": user_id,
                  "primaryParty": primary_party,
                  "isDeactivated": False,
                  "identityProviderId": ""},
         "rights": rights},
        sub=c8lab.ADMIN)


def _user_rights(user_id):
    quoted = urllib.parse.quote(user_id, safe="")
    return c8lab.call(
        f"/v2/users/{quoted}/rights", sub=c8lab.ADMIN).get("rights", [])


def _right_pairs(rights):
    pairs = set()
    for right in rights:
        kinds = right.get("kind", {})
        if len(kinds) != 1:
            continue
        kind, details = next(iter(kinds.items()))
        party = (details or {}).get("value", {}).get("party")
        pairs.add((kind, party))
    return pairs


def _active_events(party, template_id, sub):
    body = {"filter": {"filtersByParty": {party: {"cumulative": [
                {"identifierFilter": {"TemplateFilter": {"value": {
                    "templateId": template_id,
                    "includeCreatedEventBlob": False}}}}]}}},
            "verbose": False,
            "activeAtOffset": c8lab.ledger_end(sub)}
    events = []
    for item in c8lab.call("/v2/state/active-contracts", body, sub=sub):
        event = (item.get("contractEntry", {})
                 .get("JsActiveContract", {}).get("createdEvent"))
        if event:
            events.append(event)
    return events


def _active_interface_events(party, interface_id, sub):
    body = {"filter": {"filtersByParty": {party: {"cumulative": [
                {"identifierFilter": {"InterfaceFilter": {"value": {
                    "interfaceId": interface_id,
                    "includeInterfaceView": True,
                    "includeCreatedEventBlob": False}}}}]}}},
            "verbose": False,
            "activeAtOffset": c8lab.ledger_end(sub)}
    events = []
    for item in c8lab.call("/v2/state/active-contracts", body, sub=sub):
        event = (item.get("contractEntry", {})
                 .get("JsActiveContract", {}).get("createdEvent"))
        if event:
            events.append(event)
    return events


def _only_contract_id(party, template_id, sub):
    events = _active_events(party, template_id, sub)
    if len(events) != 1:
        raise AssertionError(
            f"expected one active {template_id}, found {len(events)}")
    return events[0]["contractId"]


def _balance(party, instrument, admin, sub):
    return sum(
        (Decimal(holding["amount"]) for holding in
         c8lab.holdings(party, sub=sub)
         if holding["instrument"] == instrument
         and holding["admin"] == admin),
        Decimal("0"))


def _upload_mandate_dar():
    package_dir = ROOT / "daml-starter"
    subprocess.run(
        ["daml", "build"], cwd=package_dir, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    dar = package_dir / ".daml/dist/c8-agent-wallet-1.0.0.dar"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as token_file:
        token_file.write(c8lab.token(c8lab.ADMIN))
        token_file.flush()
        subprocess.run(
            ["daml", "ledger", "upload-dar",
             "--host", os.getenv("C8_GRPC_HOST", "127.0.0.1"),
             "--port", os.getenv("C8_GRPC_PORT", "2901"),
             "--access-token-file", token_file.name,
             str(dar)],
            cwd=ROOT, check=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)


def _iso(instant):
    return instant.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_charge(owner, receiver, amount, instrument, admin, expires_at,
                    resolver_user):
    owner_holdings = [
        holding for holding in
        c8lab.holdings(
            owner, sub=resolver_user, include_disclosures=True)
        if not holding["locked"]
        and holding["instrument"] == instrument
        and holding["admin"] == admin
    ]
    if sum((Decimal(h["amount"]) for h in owner_holdings), Decimal("0")) \
            < amount:
        raise AssertionError("owner does not have enough spendable Canton Coin")

    requested_at = datetime.datetime.now(datetime.timezone.utc)
    transfer = {
        "sender": owner,
        "receiver": receiver,
        "amount": str(amount),
        "instrumentId": {"admin": admin, "id": instrument},
        "requestedAt": _iso(requested_at),
        "executeBefore": _iso(expires_at),
        "inputHoldingCids": [h["contractId"] for h in owner_holdings],
        "meta": {"values": {}},
    }
    factory_args = {
        "expectedAdmin": admin,
        "transfer": transfer,
        "extraArgs": {
            "context": {"values": {}},
            "meta": {"values": {}},
        },
    }
    factory = c8lab.registry(
        "/registry/transfer-instruction/v1/transfer-factory",
        {"choiceArguments": factory_args})
    choice_context = factory.get("choiceContext", {})
    factory_args["extraArgs"]["context"] = choice_context.get(
        "choiceContextData", {})
    holding_disclosures = [
        {field: holding[field] for field in
         ("templateId", "contractId", "createdEventBlob", "synchronizerId")}
        for holding in owner_holdings
    ]
    return {
        "factory": factory,
        "factoryArgs": factory_args,
        "holdingCids": transfer["inputHoldingCids"],
        "choiceContext": factory_args["extraArgs"]["context"],
        "disclosures": (choice_context.get("disclosedContracts", [])
                        + holding_disclosures),
    }


def _wait_for_direct_charge(owner, receiver, amount, instrument, admin,
                            expires_at, resolver_user):
    deadline = time.monotonic() + 90
    last_kind = None
    while time.monotonic() < deadline:
        resolved = _resolve_charge(
            owner, receiver, amount, instrument, admin, expires_at,
            resolver_user)
        last_kind = resolved["factory"].get("transferKind")
        if last_kind == "direct":
            return resolved
        time.sleep(2)
    raise AssertionError(
        f"merchant preapproval did not become direct; last kind={last_kind!r}")


def _fund_with_contention_retry(sender, receiver, amount, instrument, sub):
    """LocalNet mining may momentarily consume the provider's same holdings."""
    deadline = time.monotonic() + 60
    while True:
        try:
            return c8lab.transfer(
                sender, receiver, amount, instrument=instrument, sub=sub)
        except c8lab.LabError as exc:
            if ("LOCAL_VERDICT_LOCKED_CONTRACTS" not in str(exc)
                    or time.monotonic() >= deadline):
                raise
            time.sleep(2)


class HoldingDisclosureResolverTests(unittest.TestCase):
    def test_disclosure_mode_requests_and_returns_event_blob(self):
        event = {
            "contractId": "holding-1",
            "templateId": "pkg:Mod:HoldingImpl",
            "createdEventBlob": "opaque-blob",
            "synchronizerId": "sync-1",
            "interfaceViews": [{"viewValue": {
                "owner": "owner::1",
                "amount": "2.5",
                "instrumentId": {"id": "Amulet", "admin": "DSO::1"},
                "lock": None,
            }}],
        }
        response = [{"contractEntry": {
            "JsActiveContract": {"createdEvent": event}}}]
        with mock.patch.object(c8lab, "ledger_end", return_value=12), \
             mock.patch.object(c8lab, "call", return_value=response) as call:
            result = c8lab.holdings(
                "owner::1", sub="resolver", include_disclosures=True)
        interface_filter = (call.call_args.args[1]["filter"]["filtersByParty"]
                            ["owner::1"]["cumulative"][0]
                            ["identifierFilter"]["InterfaceFilter"]["value"])
        self.assertTrue(interface_filter["includeCreatedEventBlob"])
        self.assertEqual("opaque-blob", result[0]["createdEventBlob"])
        self.assertEqual("pkg:Mod:HoldingImpl", result[0]["templateId"])


@unittest.skipUnless(
    os.getenv("C8_RUN_LOCALNET_INTEGRATION") == "1",
    "set C8_RUN_LOCALNET_INTEGRATION=1 to move real LocalNet Canton Coin")
class AtomicTokenChargeLocalNetTests(unittest.TestCase):
    def test_agent_charge_is_direct_atomic_and_least_privilege(self):
        if c8lab.IDP or c8lab.ACCESS_TOKEN:
            self.fail("this integration proof requires operator-side LocalNet auth")
        _upload_mandate_dar()

        run_id = os.getenv("C8_INTEGRATION_RUN_ID", str(int(time.time())))
        owner = c8lab.allocate_party(
            f"atomic-owner-{run_id}", sub=c8lab.ADMIN, grant_to=None)
        agent = c8lab.allocate_party(
            f"atomic-agent-{run_id}", sub=c8lab.ADMIN, grant_to=None)
        merchant = c8lab.allocate_party(
            f"atomic-merchant-{run_id}", sub=c8lab.ADMIN, grant_to=None)
        offer_merchant = c8lab.allocate_party(
            f"atomic-offer-{run_id}", sub=c8lab.ADMIN, grant_to=None)

        owner_user = f"atomic-owner-{run_id}"
        agent_user = f"atomic-agent-{run_id}"
        merchant_user = f"atomic-merchant-{run_id}"
        offer_user = f"atomic-offer-{run_id}"
        resolver_user = f"atomic-resolver-{run_id}"
        _create_user(owner_user, owner, [_right("CanActAs", owner)])
        _create_user(agent_user, agent, [_right("CanActAs", agent)])
        _create_user(merchant_user, merchant, [_right("CanActAs", merchant)])
        _create_user(
            offer_user, offer_merchant,
            [_right("CanActAs", offer_merchant)])
        _create_user(
            resolver_user, owner, [_right("CanReadAs", owner)])

        self.assertEqual(
            {("CanActAs", agent)}, _right_pairs(_user_rights(agent_user)))
        self.assertEqual(
            {("CanReadAs", owner)},
            _right_pairs(_user_rights(resolver_user)))

        instrument = "Amulet"
        admin = c8lab.admin_party()
        provider = c8lab.find_party("app_user", sub=c8lab.ADMIN)
        c8lab.create_preapproval_proposal(
            owner, provider, sub=owner_user)
        funding = _fund_with_contention_retry(
            provider, owner, "1.0", instrument, c8lab.USER)
        if funding["transferKind"] == "offer":
            self.assertTrue(funding["instructionCid"])
            c8lab.accept_transfer(
                funding["instructionCid"], owner, sub=owner_user)
        self.assertGreaterEqual(
            _balance(owner, instrument, admin, resolver_user), Decimal("1.0"))

        # The merchant preapproval is what makes Charge settle immediately.
        c8lab.create_preapproval_proposal(
            merchant, provider, sub=merchant_user)

        expires_at = (datetime.datetime.now(datetime.timezone.utc)
                      + datetime.timedelta(hours=1))
        proposal_args = {
            "mandateId": f"localnet-atomic-{run_id}",
            "owner": owner,
            "agent": agent,
            "instrumentId": instrument,
            "expectedAdmin": admin,
            "totalCap": "1.0",
            "allowedCounterparties": [merchant, offer_merchant],
            "expiresAt": _iso(expires_at),
        }
        c8lab.submit(
            [{"CreateCommand": {
                "templateId": MANDATE_PROPOSAL,
                "createArguments": proposal_args}}],
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
        usage_cid = _only_contract_id(agent, MANDATE_USAGE, agent_user)

        charge_amount = Decimal("0.1")
        direct = _wait_for_direct_charge(
            owner, merchant, charge_amount, instrument, admin, expires_at,
            resolver_user)
        self.assertEqual("direct", direct["factory"].get("transferKind"))

        owner_before = _balance(owner, instrument, admin, resolver_user)
        merchant_before = _balance(
            merchant, instrument, admin, merchant_user)

        # The same factory transfer is unauthorized as an agent root command.
        with self.assertRaises(c8lab.LabError):
            c8lab.submit(
                [{"ExerciseCommand": {
                    "templateId": c8lab.TRANSFER_FACTORY,
                    "contractId": direct["factory"]["factoryId"],
                    "choice": "TransferFactory_Transfer",
                    "choiceArgument": direct["factoryArgs"]}}],
                act_as=agent, sub=agent_user,
                disclosed=direct["disclosures"])
        self.assertEqual(
            owner_before, _balance(owner, instrument, admin, resolver_user))
        self.assertEqual(
            merchant_before,
            _balance(merchant, instrument, admin, merchant_user))

        wallet_agent = MandateAgent(
            agent,
            C8LedgerClient(agent, agent_user),
            C8TokenResolver(resolver_user))
        outcome = wallet_agent.charge(
            proposal_args["mandateId"],
            PurchaseRequest(
                merchant=merchant,
                amount=charge_amount,
                business_reference=f"direct-{run_id}"))
        self.assertEqual("committed", outcome.status)
        self.assertIsNotNone(outcome.receipt)

        owner_after = _balance(owner, instrument, admin, resolver_user)
        merchant_after = _balance(
            merchant, instrument, admin, merchant_user)
        self.assertLessEqual(owner_after, owner_before - charge_amount)
        self.assertEqual(merchant_before + charge_amount, merchant_after)
        self.assertEqual(
            1, len(_active_events(agent, CHARGE_RECEIPT, agent_user)))
        usage_after_direct = _only_contract_id(
            agent, MANDATE_USAGE, agent_user)
        self.assertNotEqual(usage_cid, usage_after_direct)

        # A receiver without preapproval produces an offer/Pending result.
        # Charge aborts it, so no instruction, receipt, spend, or usage advance
        # survives the transaction.
        pending_amount = Decimal("0.05")
        pending = _resolve_charge(
            owner, offer_merchant, pending_amount, instrument, admin,
            expires_at, resolver_user)
        self.assertEqual("offer", pending["factory"].get("transferKind"))
        receipt_count = len(_active_events(
            agent, CHARGE_RECEIPT, agent_user))
        owner_before_pending = _balance(
            owner, instrument, admin, resolver_user)
        offer_before = _balance(
            offer_merchant, instrument, admin, offer_user)
        with self.assertRaises(c8lab.LabError):
            c8lab.submit(
                [{"ExerciseCommand": {
                    "templateId": MANDATE_USAGE,
                    "contractId": usage_after_direct,
                    "choice": "Charge",
                    "choiceArgument": {
                        "merchant": offer_merchant,
                        "amount": str(pending_amount),
                        "businessReference": f"pending-{run_id}",
                        "tokenExecution": {
                            "transferFactoryCid":
                                pending["factory"]["factoryId"],
                            "inputHoldingCids": pending["holdingCids"],
                            "choiceContext": pending["choiceContext"],
                        },
                    }}}],
                act_as=agent, sub=agent_user,
                disclosed=pending["disclosures"])

        self.assertEqual(
            usage_after_direct,
            _only_contract_id(agent, MANDATE_USAGE, agent_user))
        self.assertEqual(
            receipt_count,
            len(_active_events(agent, CHARGE_RECEIPT, agent_user)))
        self.assertEqual(
            owner_before_pending,
            _balance(owner, instrument, admin, resolver_user))
        self.assertEqual(
            offer_before,
            _balance(offer_merchant, instrument, admin, offer_user))
        self.assertEqual(
            [], _active_interface_events(
                offer_merchant, c8lab.TRANSFER_INSTRUCTION, offer_user))


if __name__ == "__main__":
    unittest.main()
