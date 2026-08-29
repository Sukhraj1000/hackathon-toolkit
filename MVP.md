# Agent wallet MVP

The MVP is deliberately one LocalNet happy path: a fresh owner authorizes one
agent to pay one merchant, the agent purchases `0.1 Amulet`, and the command
prints the ledger receipt and remaining allowance. It then attempts one charge
above the remaining cap and proves that the wallet rejects it before token
resolution or submission.

## Run it

Start Splice LocalNet as described in `SETUP.md`, install the Daml CLI, and make
sure DevNet credentials are unset. Then verify the environment and run:

```bash
python3 agent_wallet_mvp.py doctor
python3 agent_wallet_mvp.py demo
```

The command builds and uploads the existing mandate DAR, provisions fresh
least-privilege users, funds the owner with LocalNet test Canton Coin, waits for
the merchant preapproval, and executes the existing `MandateAgent` flow. It
does not persist credentials. It writes only party IDs, user IDs, and the
mandate ID to the ignored `.c8wallet-state.json` file so subsequent commands
can address the same ledger state.

Successful output ends with a receipt contract ID, a ledger reference, the
remaining mandate allowance, and an over-cap rejection:

```text
AGENT WALLET MVP COMPLETE
purchase         0.1 Amulet
receipt          00...
ledger reference 12...
allowance        0.1 / 1.0 spent
remaining        0.9 Amulet
safety check     rejected: charge exceeds remaining mandate cap
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

`status` and `statement` read the current mandate and receipts from the ledger.
`buy` submits only `MandateUsage.Charge` as the state-bound agent. It accepts no
identity, owner credential, template, choice, or arbitrary command override.
An optional `--merchant` must be the exact canonical Party ID and remains
subject to the on-ledger allow-list.

Running `python3 agent_wallet_mvp.py` without a subcommand remains equivalent to
`python3 agent_wallet_mvp.py demo`.

## Intentionally out of scope

This command does not add a UI, merchant discovery, multi-machine networking,
DevNet provisioning, production authentication, owner mandate management, or a
full adversarial test suite. Those can build on the validated ledger path after
the MVP lands.
