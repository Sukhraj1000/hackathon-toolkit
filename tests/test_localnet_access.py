import contextlib
import io
from pathlib import Path
import unittest
from unittest import mock
import urllib.error

import agent_wallet_localnet
import c8lab
from scripts import verify_tailscale_serve_config
from scripts import verify_team_access


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

    def test_preminted_check_uses_only_configured_party(self):
        party = self.parties["agent"]
        with mock.patch.object(c8lab, "ACCESS_TOKEN", "agent-token"), \
             mock.patch.object(c8lab, "CONFIGURED_PARTY", party), \
             mock.patch.object(c8lab, "token"), \
             mock.patch.object(c8lab, "ledger_end", return_value=1), \
             mock.patch.object(c8lab, "holdings", return_value=[]) as holdings, \
             mock.patch.object(c8lab, "local_parties") as local_parties:
            with contextlib.redirect_stdout(io.StringIO()):
                c8lab.check()
        holdings.assert_called_once_with(party)
        local_parties.assert_not_called()

    def test_preminted_check_requires_configured_party(self):
        with mock.patch.object(c8lab, "ACCESS_TOKEN", "agent-token"), \
             mock.patch.object(c8lab, "CONFIGURED_PARTY", ""):
            with self.assertRaises(c8lab.LabError):
                with contextlib.redirect_stdout(io.StringIO()):
                    c8lab.check()

    def test_preminted_check_rejects_inaccessible_party(self):
        party = self.parties["owner"]
        with mock.patch.object(c8lab, "ACCESS_TOKEN", "agent-token"), \
             mock.patch.object(c8lab, "CONFIGURED_PARTY", party), \
             mock.patch.object(c8lab, "token"), \
             mock.patch.object(c8lab, "ledger_end", return_value=1), \
             mock.patch.object(
                 c8lab, "holdings",
                 side_effect=c8lab.LabError("HTTP 403")):
            with self.assertRaises(c8lab.LabError):
                with contextlib.redirect_stdout(io.StringIO()):
                    c8lab.check()


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
        self.assertIn("C8_PARTY", values)
        self.assertTrue(agent_wallet_localnet.PRIVILEGED_RIGHTS)
        for forbidden in ("C8_JWT_SECRET", "C8_CLIENT_SECRET", "C8_OWNER_TOKEN"):
            self.assertNotIn(forbidden, values)

    def test_serve_config_rejects_unexpected_listener(self):
        config = {"TCP": {
            "2975": {"TCPForward": "127.0.0.1:2975"},
            "443": {"HTTPS": True},
        }}
        errors = verify_tailscale_serve_config.validate(
            config, allow_missing=True)
        self.assertTrue(any("443" in error for error in errors))

    def test_serve_config_requires_exact_forwards(self):
        config = {"TCP": {
            "2975": {"TCPForward": "127.0.0.1:9999"},
            "8401": {"TCPForward": "127.0.0.1:8401"},
        }}
        errors = verify_tailscale_serve_config.validate(config)
        self.assertTrue(any("9999" in error for error in errors))

    def test_remote_probe_accepts_expected_http_statuses(self):
        unauthorized = urllib.error.HTTPError(
            "http://host:2975/v2/state/ledger-end", 401,
            "Unauthorized", {}, None)
        with mock.patch.object(
                verify_team_access.urllib.request, "urlopen",
                side_effect=unauthorized):
            self.assertEqual(
                401, verify_team_access.http_status(
                    "host", 2975, "/v2/state/ledger-end", 1))

        response = mock.MagicMock()
        response.__enter__.return_value.status = 200
        with mock.patch.object(
                verify_team_access.urllib.request, "urlopen",
                return_value=response):
            self.assertEqual(
                200, verify_team_access.http_status(
                    "host", 8401, "/health", 1))

    def test_remote_probe_covers_custom_gateway_ports(self):
        for port in (8200, 8302, 8400):
            self.assertIn(port, verify_team_access.FORBIDDEN_PORTS)


if __name__ == "__main__":
    unittest.main()
