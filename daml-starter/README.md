# Daml starter

This package contains a ledger-enforced spending mandate for one owner and one
designated agent. The API is not the authorization boundary: cap, merchant,
expiry, and revocation rules are checked by Daml.

## Build and test

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
export PATH="$HOME/.daml/bin:$JAVA_HOME/bin:$PATH"

daml build
daml test
```

The tests run against the in-memory Daml Script ledger and require no Docker or
external ledger.

## Contract flow

```text
MandateProposal                  owner offers a complete policy
  -> Accept                      designated agent accepts
      -> Mandate                 immutable authorization policy
      -> MandateUsage            mutable state with spent = 0

MandateUsage
  -> Charge                      designated agent only
      -> fetch Mandate           proves authorization remains active
      -> MandateUsage            successor with exact cumulative spend
      -> ChargeReceipt           immutable committed-charge evidence

Mandate
  -> Revoke                      owner only; archives the policy immediately
```

`Mandate` pins the owner, agent, token instrument, expected token administrator,
lifetime cap, merchant allow-list, and expiry. The owner is its signatory and
the agent is an observer. Policy never changes after acceptance.

`MandateUsage` is the single mutable state for that policy. `Charge` is a
consuming choice controlled only by the designated agent. It fetches the static
mandate, checks the requested purchase, then creates the usage successor and
receipt in one transaction.

## Ledger-enforced checks

The security boundary is in `MandateUsage.Charge`:

```daml
mandate <- fetch mandateCid
assertMsg "amount must be positive" (amount > 0.0)
assertMsg "counterparty not allowed"
  (merchant `elem` mandate.allowedCounterparties)
assertMsg "total cap exceeded" (spentAfter <= mandate.totalCap)
assertMsg "mandate expired" (now < mandate.expiresAt)
```

The agent supplies only `merchant`, `amount`, and a business reference. Owner,
agent, instrument, administrator, cap, allow-list, and expiry come from ledger
contracts rather than client input.

Archiving `Mandate` revokes immediately. A remaining `MandateUsage` cannot be
charged because the first action in `Charge` is fetching that archived mandate.
Consuming usage also serializes charges: once one command commits, another
command holding the old usage contract ID is stale and cannot commit.

## Audit receipts

Every successful charge creates one `ChargeReceipt` containing the mandate
reference, owner, agent, merchant, instrument, amount, spend before and after,
ledger time, and business reference. Rejected commands create no receipt and do
not advance usage.

## Test coverage

`daml/Test.daml` proves:

- owner/agent signatory, observer, and controller boundaries;
- grant acceptance and owner-only revocation;
- under-cap and exact-cap charges;
- zero, negative, over-cap, wrong-merchant, wrong-agent, expired, and revoked
  charges are rejected;
- rejected and stale commands leave authorization, usage, and receipt state
  unchanged;
- forged usage contracts cannot substitute another owner or agent;
- receipts expose complete audit data only to their stakeholders.

Real Token Standard settlement is intentionally separate. The next integration
step should perform the transfer inside `Charge`, in the same transaction as the
usage successor and receipt.
