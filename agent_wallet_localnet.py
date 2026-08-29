#!/usr/bin/env python3
"""Provision and verify the demo's least-privilege LocalNet identities.

This is an operator command. Run it on the LocalNet host, never inside the
AI-facing process. It is stdlib-only and deliberately does not write tokens or
credentials to disk.
"""

import argparse
import sys
import urllib.parse

import c8lab


ROLE_SPECS = {
    "owner": {"party_hint": "wallet-owner-1", "user": "wallet-owner"},
    "agent": {"party_hint": "wallet-agent-1", "user": "wallet-agent"},
    "merchant": {"party_hint": "wallet-merchant-1", "user": "wallet-merchant"},
}

PRIVILEGED_RIGHTS = {
    "CanActAsAnyParty",
    "CanExecuteAsAnyParty",
    "CanReadAsAnyParty",
    "IdentityProviderAdmin",
    "ParticipantAdmin",
}


def _right_kind_and_party(right):
    kinds = right.get("kind", {})
    if len(kinds) != 1:
        return "Unknown", None
    kind, details = next(iter(kinds.items()))
    party = (details or {}).get("value", {}).get("party")
    return kind, party


def _act_as_right(party):
    return {"kind": {"CanActAs": {"value": {"party": party}}}}


def _users():
    return c8lab.call("/v2/users", sub=c8lab.ADMIN).get("users", [])


def _rights(user_id):
    quoted = urllib.parse.quote(user_id, safe="")
    return c8lab.call(
        f"/v2/users/{quoted}/rights", sub=c8lab.ADMIN).get("rights", [])


def _ensure_user(user_id, party):
    existing = {user.get("id") for user in _users()}
    if user_id not in existing:
        c8lab.call(
            "/v2/users",
            {"user": {"id": user_id,
                      "primaryParty": party,
                      "isDeactivated": False,
                      "identityProviderId": ""},
             "rights": [_act_as_right(party)]},
            sub=c8lab.ADMIN)
    else:
        c8lab.grant_act_as(user_id, party, sub=c8lab.ADMIN)


def audit_assignments(parties, rights_by_user):
    """Return human-readable least-privilege violations."""
    errors = []
    for role, spec in ROLE_SPECS.items():
        user_id = spec["user"]
        expected_party = parties[role]
        rights = rights_by_user.get(user_id, [])
        parsed = [_right_kind_and_party(right) for right in rights]
        act_as = {party for kind, party in parsed
                  if kind == "CanActAs" and party}
        kinds = {kind for kind, _ in parsed}

        if expected_party not in act_as:
            errors.append(
                f"{user_id} is missing CanActAs({expected_party})")
        unexpected = sorted(act_as - {expected_party})
        if unexpected:
            errors.append(
                f"{user_id} can act as an unexpected party: "
                + ", ".join(unexpected))

        unexpected_scoped = sorted(
            f"{kind}({party})"
            for kind, party in parsed
            if kind in {"CanExecuteAs", "CanReadAs"}
            and party != expected_party)
        if unexpected_scoped:
            errors.append(
                f"{user_id} has unexpected scoped rights: "
                + ", ".join(unexpected_scoped))
        privileged = sorted(kinds & PRIVILEGED_RIGHTS)
        if privileged:
            errors.append(
                f"{user_id} has forbidden broad rights: "
                + ", ".join(privileged))
    return errors


def audit_users(parties, users):
    """Verify that each role has one active user with the expected primary party."""
    errors = []
    users_by_id = {user.get("id"): user for user in users}
    for role, spec in ROLE_SPECS.items():
        user_id = spec["user"]
        user = users_by_id.get(user_id)
        if not user:
            errors.append(f"ledger user {user_id} does not exist")
            continue
        if user.get("isDeactivated"):
            errors.append(f"ledger user {user_id} is deactivated")
        if user.get("primaryParty") != parties[role]:
            errors.append(
                f"{user_id} primary party is {user.get('primaryParty')!r}, "
                f"expected {parties[role]!r}")
    return errors


def resolve_parties(apply):
    parties = {}
    for role, spec in ROLE_SPECS.items():
        if apply:
            parties[role] = c8lab.allocate_party(
                spec["party_hint"], sub=c8lab.ADMIN, grant_to=None)
        else:
            parties[role] = c8lab.find_party(
                spec["party_hint"], sub=c8lab.ADMIN)
    return parties


def run(apply=False):
    if c8lab.IDP:
        raise c8lab.LabError(
            "this bootstrap is LocalNet-only; provision production identities "
            "through the real identity provider")
    if c8lab.ACCESS_TOKEN:
        raise c8lab.LabError(
            "unset C8_ACCESS_TOKEN before running the operator bootstrap")

    parties = resolve_parties(apply)
    if apply:
        for role, spec in ROLE_SPECS.items():
            _ensure_user(spec["user"], parties[role])

    users = _users()
    rights_by_user = {
        spec["user"]: _rights(spec["user"])
        for spec in ROLE_SPECS.values()
    }
    errors = audit_users(parties, users)
    errors.extend(audit_assignments(parties, rights_by_user))
    if errors:
        raise c8lab.LabError(
            "least-privilege verification failed:\n  - "
            + "\n  - ".join(errors)
            + "\nUse fresh user IDs or revoke the unexpected rights manually; "
              "this command never removes rights automatically.")

    print("LocalNet wallet identities verified:\n")
    print(f"{'role':<10} {'ledger user':<18} party")
    for role, spec in ROLE_SPECS.items():
        print(f"{role:<10} {spec['user']:<18} {parties[role]}")
    print("\nEach user can act only as its matching wallet party.")
    print("The wallet-agent user cannot act as the owner or merchant.")


def main():
    parser = argparse.ArgumentParser(
        description="Provision or verify agent-wallet LocalNet identities")
    parser.add_argument(
        "--apply", action="store_true",
        help="allocate missing parties/users and grant their one expected right")
    args = parser.parse_args()
    try:
        run(apply=args.apply)
    except c8lab.LabError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
