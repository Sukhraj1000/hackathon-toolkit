from pathlib import Path
import unittest
from unittest import mock

import agent_wallet_localnet
import c8lab


ROOT = Path(__file__).resolve().parents[1]


class IdentityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.parties = {
            "owner": "wallet-owner-1::owner",
            "agent": "wallet-agent-1::agent",
            "merchant": "wallet-merchant-1::merchant",
        }

    @staticmethod
    def right(kind, party=None):
        value = {"party": party} if party else {}
        return {"kind": {kind: {"value": value}}}

    def expected_rights(self):
        return {
            spec["user"]: [self.right("CanActAs", self.parties[role])]
            for role, spec in agent_wallet_localnet.ROLE_SPECS.items()
        }

    def test_expected_role_rights_pass(self):
        self.assertEqual(
            [], agent_wallet_localnet.audit_assignments(
                self.parties, self.expected_rights()))

    def test_agent_cannot_act_as_owner(self):
        rights = self.expected_rights()
        rights["wallet-agent"].append(
            self.right("CanActAs", self.parties["owner"]))
        errors = agent_wallet_localnet.audit_assignments(self.parties, rights)
        self.assertTrue(any("unexpected party" in error for error in errors))

    def test_agent_cannot_act_as_an_unrelated_party(self):
        rights = self.expected_rights()
        rights["wallet-agent"].append(
            self.right("CanActAs", "unrelated::party"))
        errors = agent_wallet_localnet.audit_assignments(self.parties, rights)
        self.assertTrue(any("unrelated::party" in error for error in errors))

    def test_agent_cannot_read_as_owner(self):
        rights = self.expected_rights()
        rights["wallet-agent"].append(
            self.right("CanReadAs", self.parties["owner"]))
        errors = agent_wallet_localnet.audit_assignments(self.parties, rights)
        self.assertTrue(any("unexpected scoped rights" in error
                            for error in errors))

    def test_agent_cannot_be_participant_admin(self):
        rights = self.expected_rights()
        rights["wallet-agent"].append(self.right("ParticipantAdmin"))
        errors = agent_wallet_localnet.audit_assignments(self.parties, rights)
        self.assertTrue(any("ParticipantAdmin" in error for error in errors))

    def test_users_are_active_with_expected_primary_parties(self):
        users = [
            {"id": spec["user"], "primaryParty": self.parties[role],
             "isDeactivated": False}
            for role, spec in agent_wallet_localnet.ROLE_SPECS.items()
        ]
        self.assertEqual(
            [], agent_wallet_localnet.audit_users(self.parties, users))

    def test_wrong_primary_party_is_rejected(self):
        users = [
            {"id": spec["user"], "primaryParty": self.parties[role],
             "isDeactivated": False}
            for role, spec in agent_wallet_localnet.ROLE_SPECS.items()
        ]
        users[1]["primaryParty"] = self.parties["owner"]
        errors = agent_wallet_localnet.audit_users(self.parties, users)
        self.assertTrue(any("primary party" in error for error in errors))

    def test_preminted_token_cannot_be_reused_as_admin(self):
        with mock.patch.object(c8lab, "ACCESS_TOKEN", "agent-token"), \
             mock.patch.object(c8lab, "USER", "wallet-agent"):
            self.assertEqual("agent-token", c8lab.token("wallet-agent"))
            with self.assertRaises(c8lab.LabError):
                c8lab.token(c8lab.ADMIN)


class NetworkBoundaryTests(unittest.TestCase):
    def test_tailnet_grant_has_only_two_ports(self):
        policy_text = (ROOT / "deployment/tailscale-policy.example.hujson").read_text()
        self.assertIn('"ip": ["tcp:2975", "tcp:8401"]', policy_text)
        self.assertEqual(1, policy_text.count('"ip":'))

    def test_gateway_publishes_only_registry_port(self):
        override = (ROOT / "deployment/localnet-loopback.override.yaml").read_text()
        gateway = override.split("  team-gateway:", 1)[1]
        self.assertIn('"127.0.0.1:8401:8401"', gateway)
        self.assertNotIn(":2975:2975", gateway)
        self.assertNotIn(":5432:5432", gateway)

    def test_agent_environment_example_contains_no_secret(self):
        values = {}
        for line in (ROOT / "deployment/agent.env.example").read_text().splitlines():
            if line and not line.startswith("#"):
                name, value = line.split("=", 1)
                values[name] = value
        self.assertIn("C8_ACCESS_TOKEN", values)
        self.assertTrue(agent_wallet_localnet.PRIVILEGED_RIGHTS)
        for forbidden in ("C8_JWT_SECRET", "C8_CLIENT_SECRET", "C8_OWNER_TOKEN"):
            self.assertNotIn(forbidden, values)


if __name__ == "__main__":
    unittest.main()
