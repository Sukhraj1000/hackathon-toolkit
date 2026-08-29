# Daml starter

This directory builds the submission package `c8-agent-wallet` version `1.0.0`.
It contains a ledger-enforced spending mandate for one owner and one designated
agent. The API is not the authorization boundary: cap, merchant, expiry, and
revocation rules are checked by Daml.

## Build and test

From the repository root:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
export PATH="$HOME/.daml/bin:$JAVA_HOME/bin:$PATH"

daml build --all
(cd daml-starter-test && daml test)
python3 -m unittest discover -s tests -v
```

The Daml tests run against the in-memory Script ledger and require no Docker.
Production contracts and test-only token implementations are separate packages,
so the mock factory and holding cannot be uploaded with the mandate DAR.

## Contract flow

```text
MandateProposal                  owner offers a complete policy
  -> Accept                      designated agent accepts
      -> Mandate                 immutable authorization policy
      -> MandateUsage            jointly signed policy snapshot and spend state

MandateUsage
  -> Charge                      designated agent only
      -> fetch Mandate           proves authorization remains active
      -> validate Holding views  owner, instrument/admin, lock, and coverage
      -> TransferFactory         real Token Standard V1 direct transfer
      -> MandateUsage            successor with spend and replay marker
      -> ChargeReceipt           immutable committed-charge evidence

Mandate
  -> Revoke                      owner only; archives the policy immediately
```

`Mandate` pins a stable owner-issued mandate ID, the owner, agent, token
instrument, expected token administrator, lifetime cap, merchant allow-list,
and expiry. The owner is its signatory and the agent is an observer. Policy
never changes after acceptance.

`MandateUsage` is jointly signed by the owner and designated agent, so neither
party can fabricate a replacement state alone. `Charge` is a consuming choice
controlled only by the designated agent. It fetches the static mandate, checks
that its retained policy snapshot still exactly matches, checks the requested
purchase, then creates the usage successor and receipt in one
transaction. Token movement is not a later API side effect: a completed direct
`TransferFactory_Transfer`, the usage successor, and the receipt all commit in
the same transaction. A pending or failed transfer aborts the whole charge.

## Ledger-enforced checks

The security boundary is in `MandateUsage.Charge`:

```daml
mandate <- fetch mandateCid
assertMsg "usage mandate id does not match mandate"
  (mandateId == mandate.mandateId)
assertMsg "amount must be positive" (amount > 0.0)
assertMsg "business reference already processed"
  (businessReference `notElem` processedReferences)
assertMsg "counterparty not allowed"
  (merchant `elem` mandate.allowedCounterparties)
assertMsg "total cap exceeded" (spentAfter <= mandate.totalCap)
assertMsg "mandate expired" (now < mandate.expiresAt)
```

The agent supplies the purchase data plus opaque registry output in
`TokenExecution`: a factory CID, owner Holding CIDs, and `ChoiceContext`. The
material transfer fields are not trusted from that input. `Charge` derives
sender, receiver, amount, full `InstrumentId`, request time, and deadline from
the checked mandate and choice arguments. It fetches every Holding interface,
rejects a wrong owner/instrument/admin, locked or non-positive holding, checks
aggregate coverage, and binds the factory to `expectedAdmin` with
`TransferFactory_PublicFetch` before exercising it.

The transfer has `sender = mandate.owner`, so `TransferFactory_Transfer` still
requires owner authorization. The agent submits only as the designated agent;
the jointly signed, consuming `MandateUsage.Charge` supplies the ledger
authorization context. Calling the same transfer factory directly as the agent
is rejected.

Archiving `Mandate` revokes immediately. A remaining `MandateUsage` cannot be
charged because the first action in `Charge` is fetching that archived mandate.
The usage contract deliberately retains the immutable instrument, administrator,
cap, counterparty allow-list, and expiry so a ledger-derived human statement
remains complete after revocation; it is terminal audit state, not usable
authorization.
Consuming usage also serializes charges: once one command commits, another
command holding the old usage contract ID is stale and cannot commit. Every
successor carries all processed business references, so a reference cannot be
replayed later in the chain. This persistent state is used because unique Daml
contract keys are not supported on Canton 3.x.

## Audit receipts

Every successful charge creates one `ChargeReceipt` containing the mandate
reference and stable ID, owner, agent, merchant, instrument, amount, spend
before and after, ledger time, and business reference. Owner and agent are both
receipt signatories, so neither can fabricate one alone. Rejected commands
create no receipt and do not advance usage.

## Test coverage

`daml/Test.daml` proves:

- owner/agent signatory, observer, and controller boundaries;
- grant acceptance and owner-only revocation;
- under-cap and exact-cap charges, including the maximum reference length;
- zero, negative, over-cap, wrong-merchant, wrong-agent, expired, and revoked
  charges are rejected;
- empty, whitespace-only, oversized, and duplicate business references are
  rejected without changing spend or receipts;
- rejected and stale commands leave authorization, usage, and receipt state
  unchanged;
- forged usage contracts cannot substitute another mandate ID, owner, or agent;
- neither owner nor agent can create replacement usage alone, and the owner
  cannot fabricate a receipt alone;
- both charge-versus-revoke ledger orderings preserve the intended outcome;
- receipts expose complete audit data only to their stakeholders.
- successful charges reduce owner token balance and increase merchant balance;
- pending/failed transfer results, insufficient coverage, a wrong holding
  owner or instrument, and a factory with the wrong administrator roll back
  holdings, usage, and receipts together.

## Real LocalNet proof

The opt-in integration case uploads only the production DAR, funds a fresh
owner with real LocalNet Canton Coin, and creates distinct owner, agent,
merchant, and resolver ledger users. The agent has only `CanActAs(agent)`; the
resolver has only `CanReadAs(owner)` and returns transaction-scoped Holding
disclosures. The test proves a direct transfer changes both balances and an
offer/Pending result leaves no instruction, balance change, receipt, or usage
advance.

With Splice LocalNet 0.6.8 running on the documented default ports:

```bash
C8_RUN_LOCALNET_INTEGRATION=1 \
  python3 -m unittest discover -s tests \
    -p 'test_atomic_token_charge_localnet.py' -v
```

Set `C8_GRPC_HOST` or `C8_GRPC_PORT` only if DAR upload is not at
`127.0.0.1:2901`. This test allocates ledger state and moves LocalNet tokens;
normal unit-test discovery skips it.

The pinned Token Standard V1 interface DAR provenance and checksums are in
[`dars/README.md`](dars/README.md).
