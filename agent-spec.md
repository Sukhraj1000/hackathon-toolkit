# Agent Spec — AI Wallet (ledger-enforced limits)

## Purpose
Agent acts as `agentParty` to purchase `Offer`s under an on-ledger `Mandate`. All spend limits (total, per-purchase, approved vendors, expiry, revocation) are enforced by Daml/Canton; the agent performs decisioning, submission, retries, reconciliation and owner interactions.

## Scope & Assumptions
- Daml team provides templates: `Mandate`, `Offer`, `Receipt`, `AccessRight`, token `Holding`, optional `TransferPreapproval`.
- Agent submits commands only as `agentParty` via the Ledger API and sees only the Active Contract Set (ACS) it is authorized to view.
- Security (keys, credentials) and smart-contract correctness are owned by other teams.

## Quick Overview (Workflow)
Event-driven loop: **Observe → Decide → Build → Submit → Reconcile**

Modes:
- Autonomous: agent auto-submits offers within on-ledger limits (suitable for low-value purchases).
- Approval: agent proposes off-ledger and waits owner approval for higher-value purchases.

## Inputs (what the agent consumes)
- On-ledger (ACS visible to agent):
  - `Mandate` — fields: `ownerParty`, `agentParty`, `totalLimit`, `perPurchaseLimit`, `approvedSellers[]`, `expiry`, `revocable`.
  - `Offer` — `offerId`, `vendorParty`, `price`, `currency`, `metadata`, `expiry`.
  - `Holding` / UTXOs: token contracts and amounts available or preapproved for spending.
  - `Receipt`s and `AccessRight`s: historical purchases to compute allowance used.
  - Optional: `TransferPreapproval`, `Registry` entries.
- Ledger API & runtime metadata: submit results (success/rejection), transaction events (created/archived IDs and blinding info).
- Off-ledger: owner policy (approval thresholds), market/reputation data, local pending command state, and human approvals when required.

## Outputs (what the agent produces)
- Ledger commands (primary): `exercise` choices (e.g., `Buy` on `Offer` or `RequestPurchase` on `Mandate`), optional `create TransferPreapproval`.
- Off-ledger: owner notifications (proposal, success, rejection), audit logs, local cache updates, observability events with `commandId` and `txId`.

## State Machine (minimal)
- `Idle` → `CandidateSelected` → `CommandBuilt` → `Pending` → `Success` | `Rejected` → {`Retry` (with backoff) | `EscalateToOwner`}.

## Decision Policy (example rules)
- Filter offers where vendor ∉ `Mandate.approvedSellers`, price > `perPurchaseLimit`, price > remaining allowance, or offer expired.
- Sort by price ascending, then vendor reputation.
- If price > `ownerApprovalThreshold` → Approval Mode: propose to owner and await explicit consent.
- Otherwise → Autonomous Mode: submit directly.

## Command Construction & Idempotency
- Use a unique `commandId` (UUID) for every attempted ledger submission.
- Set `party` = the `agentParty` and `applicationId` = e.g., `agent-wallet`.
- Prefer `submitAndWait` for simple synchronous UX; use `submit` + event stream for high throughput.
- For retries: if Ledger does not offer built-in idempotency, treat each retry as a new `commandId` and handle duplicate side effects via ledger semantics.

## Example Ledger API Command (concise)
```json
{
  "commands": {
    "party": "AgentX",
    "commandId": "uuid-1234",
    "applicationId": "agent-wallet",
    "commands": [
      {
        "exercise": {
          "contractId": "offer-123",
          "choice": "Buy",
          "argument": { "price": 18, "buyer": "AgentX", "correlationId": "uuid-1234" }
        }
      }
    ]
  }
}
```

## Ledger-Enforced Checks (canonical)
The Daml/Canton contracts should enforce these invariants atomically at transaction time:
- Caller authority: submitting `party` must equal `Mandate.agentParty` or otherwise be authorized.
- Vendor whitelist: `vendorParty` ∈ `Mandate.approvedSellers`.
- Per-purchase limit: `price <= Mandate.perPurchaseLimit`.
- Remaining allowance: `price <= Mandate.totalLimit - sum(past receipts)` (computed on-ledger to avoid race conditions).
- Mandate validity: not expired and not revoked.
- Sufficient token availability: a set of `Holding` UTXOs or an applicable `TransferPreapproval`.
- Atomicity: payment transfer + `AccessRight` + `Receipt` creation + archival of referenced contracts all occur together or not at all.

## Common Rejection Codes & Agent Handling
- `VendorNotApproved` → Fatal: notify owner, do not retry for same offer.
- `PerPurchaseLimitExceeded` / `LimitExceeded` → Fatal for the offer: surface to owner and filter future offers accordingly.
- `MandateExpired` / `MandateRevoked` → Fatal: stop attempts and notify owner.
- `InsufficientFunds` / `UTXOSpent` → Retryable: refresh ACS, recompute holdings, and optionally retry with new `commandId`.
- `ConcurrencyFailure` / `InvalidInputs` (stale contractId) → Retryable: refresh ACS and retry.
- `AuthorizationError` → Fatal: send to security team.
- Network / transient synchronizer errors → Retry with exponential backoff.

## Reconciliation & Observability
- On success: parse transaction, extract created `AccessRight` and `Receipt`, update local allowance cache (or fetch fresh ACS), persist `commandId`, `txId`, and decision snapshot.
- On rejection: persist raw rejection body, map to user‑facing reason, log the offer snapshot and submitted payload for audit.
- Expose an owner-facing audit endpoint returning rows: `commandId`, decision inputs (offer snapshot), submitted payload, ledger response, timestamps, `txId` when available.

## Testing Strategy
- Unit tests: decision logic and allowance computation with mocked ACS and holdings.
- Integration tests: simulated ledger responses for each rejection type and for success.
- E2E: run against `LocalNet` or `DevNet` with sample DAR to confirm on-ledger enforcement.

## Security & Operational Notes
- Use short-lived credentials for ledger auth; rotate and secure private keys.
- Do not persist private contract payloads off-ledger unless owner explicitly allows it.
- Subscribe to `Mandate` archive/modify events to detect revocation immediately and cancel pending operations.
- Cap automatic retries to avoid DoS; escalate repeated failures.

## Deliverables (suggested for hackathon)
- This `agent-spec.md` (core spec).
- JSON schema for the command payloads and mapping of Daml field names to agent fields.
- Python example: ACS read, allowance computation, `submitAndWait`, rejection handling with retries (available on request).
- Mock harness for testing rejection scenarios (available on request).

---

*Prepared for the agent developer working on the AI wallet (ledger‑enforced spend limits). Feel free to ask for the Python example or JSON schema next.*
