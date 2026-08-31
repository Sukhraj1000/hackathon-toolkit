# Agent wallet MVP

The demo now has two layers. The base flow provisions a fresh owner, agent,
merchant, funded mandate, and first `Amulet` purchase on LocalNet. The automated
layer accepts a plain-language mission, evaluates public offers, and commits one
eligible purchase. A separate Proof Mode runs direct bypass attacks and
revocation against a disposable wallet so judges can see the contract boundary
working without copying IDs or command arguments.

## Run it

Start Splice LocalNet as described in `SETUP.md`, install the Daml CLI, and make
sure DevNet credentials are unset. Then verify the environment and run:

```bash
python3 agent_wallet_mvp.py doctor
python3 agent_wallet_mvp.py demo
```

The command builds and uploads `c8-agent-wallet-1.0.1.dar`, provisions fresh
least-privilege users, funds the owner with LocalNet test Canton Coin, waits for
the merchant preapproval, and executes the existing `MandateAgent` flow. It
does not persist credentials. It writes only party IDs, user IDs, and the
mandate ID to the ignored `.c8wallet-state.json` file so subsequent commands
can address the same ledger state.

Successful output ends with a receipt contract ID, a ledger reference, the
remaining mandate allowance, and a direct on-ledger over-cap rejection. The
demo deliberately bypasses its Python policy checks for that final request so
the rejection comes from `MandateUsage.Charge`:

```text
AGENT WALLET MVP COMPLETE
purchase         0.1 Amulet
receipt          00...
ledger reference 12...
allowance        0.1 / 1.0 spent
remaining        0.9 Amulet
safety check     on-ledger rejected: total cap exceeded
```

Use `--amount` and `--cap` only if you need different demo values. The cap must
be greater than the purchase amount.

## Continue from the CLI

The demo state can be queried and charged again without copying identifiers:

```bash
python3 agent_wallet_mvp.py status
python3 agent_wallet_mvp.py buy --amount 0.05 --reference second-order
python3 agent_wallet_mvp.py statement
```

`status` and `statement` read the policy, usage, and receipts from the ledger.
`MandateUsage` retains an immutable policy snapshot, so both commands continue
to show `status: revoked`, the original authorization contract, cap, expiry,
allow-list, cumulative spend, and receipts after the owner archives `Mandate`.
`buy` submits only `MandateUsage.Charge` as the state-bound agent. It accepts no
identity, owner credential, template, choice, or arbitrary command override.
An optional `--merchant` must be the exact canonical Party ID and remains
subject to the on-ledger allow-list.

Running `python3 agent_wallet_mvp.py` without a subcommand remains equivalent to
`python3 agent_wallet_mvp.py demo`.

## Run an autonomous mission

```bash
python3 agent_wallet_mvp.py mission \
  --goal "Buy the best approved data service within my remaining allowance"
```

With no extra configuration, this uses a deterministic policy planner. To let
an OpenAI model rank the public offers, set the key only in the server process:

```bash
export OPENAI_API_KEY=<your-key>
export C8_OPENAI_MODEL=gpt-5.4-nano  # optional override
```

The model receives only the mission, remaining budget, and public offer fields.
It can return only an offer ID. Trusted code maps that ID to the canonical
merchant and payment fields, checks the live mandate, and uses a deterministic
safe fallback if the model fails or suggests an ineligible offer. Canton still
enforces the counterparty, cap, expiry, controller, and atomic settlement.

## Run the judge proof

```bash
python3 agent_wallet_mvp.py proof
```

This provisions an isolated wallet and automatically proves:

1. One legitimate purchase and receipt commit atomically.
2. A direct over-cap submission is rejected by the Daml assertion.
3. A direct unapproved-counterparty submission is rejected.
4. The agent cannot exercise the owner-only `Revoke` choice.
5. The owner can revoke, and a post-revocation charge is rejected.
6. Rejected attempts add no receipts to the final ledger statement, whose
   terminal policy snapshot remains readable after revocation.

Use `--json` with either `mission` or `proof` for structured UI or automation
output.

## Intentionally out of scope

This remains a LocalNet demo with a fixed in-process offer catalog. It does not
provide production merchant discovery, DevNet provisioning, production
authentication, persistent secrets, arbitrary model tools, or a hosted wallet
service. Proof Mode is an operator demonstration and intentionally provisions
and revokes disposable test mandates.
