# Mandate agent wallet

`canton8_agent` is a standard-library Python adapter for the ledger-enforced
mandate flow in `daml-starter`. It does not reproduce policy off-ledger or ask an
AI model to authorize payments. Daml remains authoritative for merchant,
positive amount, cumulative cap, expiry, revocation, replay protection, token
compatibility, and atomic settlement.

## Security boundary

The runtime is split into two roles:

| Component | Required ledger right | Responsibility |
|---|---|---|
| Agent submitter | `CanActAs(agent)` | Read its visible mandate/usage/receipts and exercise `MandateUsage.Charge` |
| Holding resolver | `CanReadAs(owner)` | Resolve compatible owner holdings and return transaction-scoped disclosures plus registry context |

The agent never submits as the owner. A direct `TransferFactory_Transfer` with
`sender = owner` is unauthorized as an agent root command; it succeeds only as
the nested transfer inside the jointly signed `MandateUsage.Charge` transaction.

`C8TokenResolver` is the operator-side adapter. On LocalNet it can be composed
in-process for a demo. In a real deployment, expose it through a narrow service
boundary and give the AI-facing process only a client implementing the
`ResolverGateway` protocol. Never pass the resolver bearer token, owner token,
participant administrator token, unsafe JWT secret, or event blobs into prompts
or logs.

## Contract mapping

The adapter uses the deployed fields and choices directly:

| Daml | Python |
|---|---|
| `Mandate.totalCap` | `Authorization.total_cap` |
| `Mandate.allowedCounterparties` | `Authorization.allowed_counterparties` |
| `Mandate.expiresAt` | `Authorization.expires_at` |
| `MandateUsage.spent` | `Authorization.spent` |
| `MandateUsage.processedReferences` | `Authorization.processed_references` |
| terminal `MandateUsage` policy snapshot | revoked `Authorization` and statement |
| `MandateUsage.Charge` | `C8LedgerClient.submit_charge` |
| `TokenExecution` | `ResolvedCharge` |

There is deliberately no invented `Offer.Buy`, `perPurchaseLimit`, or
`approvedSellers` API. Optional offer selection produces a `PurchaseRequest`;
the resulting `Charge` is still validated on-ledger.

## Safe retries

`MandateAgent` derives one stable command ID from `(mandateId,
businessReference)` and reuses it for every attempt. Before the first submission
and after every failure, it searches for the matching `ChargeReceipt`.

- A matching receipt means the purchase already committed and is returned as
  `already_committed` without another payment.
- A receipt with the same reference but different merchant or amount is a hard
  error.
- Contention/stale-input failures refresh the current usage, holdings, factory,
  and choice context before a bounded retry.
- Ambiguous network/5xx outcomes are reconciled before retrying.
- Authorization and policy errors are terminal.

The stable business reference is the durable replay boundary. Generate it from
the upstream order or invoice identity, persist it before submitting, and never
replace it merely because a request timed out.

After revocation, the archived `Mandate` is no longer usable, but the active
terminal `MandateUsage` retains the immutable policy snapshot. The adapter marks
that authorization `revoked`, rejects it for purchases, and can still render a
fully ledger-derived statement. Every receipt also exposes its exact
`mandateCid` authorization link.

## Example

This in-process composition is suitable only for the documented unsafe
LocalNet demo:

```python
from decimal import Decimal
from canton8_agent import (
    C8LedgerClient, C8TokenResolver, MandateAgent, PurchaseRequest,
)

agent_party = "wallet-agent-1::..."
wallet = MandateAgent(
    agent_party,
    C8LedgerClient(agent_party, "wallet-agent"),
    C8TokenResolver("wallet-resolver"),
)

outcome = wallet.charge(
    "owner-issued-mandate-id",
    PurchaseRequest(
        merchant="wallet-merchant-1::...",
        amount=Decimal("0.1"),
        business_reference="invoice-2026-0042",
    ),
)
print(outcome.status, outcome.receipt)
```

With a pre-minted production token, `c8lab` refuses to reuse the agent token for
the resolver user. Keep that behavior: inject a remote resolver client instead
of weakening the credential check.

## Verification

Normal tests are stdlib-only:

```bash
python3 -m unittest discover -s tests -v
```

The opt-in LocalNet test provisions exact least-privilege users, uploads the
production DAR, proves the direct owner transfer is unauthorized to the agent,
runs the successful payment through `MandateAgent`, checks real Canton Coin
balances, and proves a Pending/offer transfer rolls back:

```bash
C8_RUN_LOCALNET_INTEGRATION=1 \
  python3 -m unittest discover -s tests \
    -p 'test_atomic_token_charge_localnet.py' -v
```

It allocates fresh LocalNet state and moves a small amount of test Canton Coin.
