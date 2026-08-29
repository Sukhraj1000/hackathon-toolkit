# Agent wallet MVP

The MVP is deliberately one LocalNet happy path: a fresh owner authorizes one
agent to pay one merchant, the agent purchases `0.1 Amulet`, and the command
prints the ledger receipt and remaining allowance. It then attempts one charge
above the remaining cap and proves that the wallet rejects it before token
resolution or submission.

## Run it

Start Splice LocalNet as described in `SETUP.md`, install the Daml CLI, and make
sure DevNet credentials are unset. Then run:

```bash
python3 agent_wallet_mvp.py
```

The command builds and uploads the existing mandate DAR, provisions fresh
least-privilege users, funds the owner with LocalNet test Canton Coin, waits for
the merchant preapproval, and executes the existing `MandateAgent` flow. It
does not persist credentials.

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

## Intentionally out of scope

This command does not add a UI, merchant discovery, multi-machine networking,
DevNet provisioning, production authentication, mandate management, or a full
adversarial test suite. Those can build on the validated ledger path after the
MVP lands.
