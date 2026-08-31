# Design: Ledger-enforced agent spend authorization

## Context

The toolkit contains a `Mandate` starter that records charges but does not move money. The submission must show that a designated agent can autonomously pay from owner-controlled holdings without receiving owner authority, while cap, counterparty, expiry, and revocation checks remain effective even if the backend is bypassed.

The team develops against one LocalNet host and reaches its forwarded APIs through Tailscale. LocalNet authentication is suitable for a demo but is not a production identity boundary.

## Security Claim and Threat Model

The design protects owner funds when the AI agent is malicious or prompt-injected, the agent-facing adapter receives crafted requests, adapter-side policy checks are removed, an agent token is used directly against the Ledger API, or an approved merchant name is spoofed with a different party ID.

The design does not claim to survive compromise of the owner credential, participant administrator, LocalNet JWT signing secret, canonical host/root account, deployed Daml package governance, or Canton consensus/cryptography. Those principals can legitimately change identity mappings, install code, or forge LocalNet users. They are trusted operator boundaries and must be kept out of the AI process and judge-facing surface.

For the hackathon, teammates with host access and the LocalNet `unsafe` signing secret are trusted operators. Judges and the AI receive neither. A production deployment must replace the shared HMAC secret with an external identity provider using asymmetric verification, issuer/audience validation, short-lived tokens, and separately managed service credentials.

### Principal map

| Principal | Ledger user | Rights | Available operations |
|---|---|---|---|
| Owner administrator | `owner-wallet-user` | `CanActAs(owner)` only | Grant and revoke mandates |
| Agent wallet runtime | `agent-wallet-user` | `CanActAs(agent)` only | Discover its mandates, exercise `Charge`, read its receipts |
| Holdings resolver | `owner-holdings-reader` | `CanReadAs(owner)` only | Select compatible owner holdings; cannot submit owner commands |
| Merchant application | distinct merchant user | Its own merchant party only | Receive/accept operations required by the token workflow |
| LocalNet operator | participant administrator | Provisioning only | Create users/parties, grant/revoke rights, deploy packages |

No runtime user may have `CanExecuteAsAnyParty`, `CanReadAsAnyParty`, participant-admin, identity-provider-admin, or a union of owner and agent rights. The application checks the actual Ledger API rights at startup and fails closed if they differ from the expected set.

## Goals / Non-Goals

### Goals

- Make Daml the sole source of truth for payment authorization.
- Enforce a lifetime cap, counterparty allow-list, expiry, and owner-only instant revocation.
- Move real Token Standard V1 value atomically with usage accounting and receipt creation.
- Keep the agent unable to act as the owner or construct a broader payment.
- Produce a clear statement and a short adversarial demo.

### Non-Goals

- Per-period limits or date-window arithmetic.
- Multiple tokens per mandate, currency conversion, or partial/pending settlement accounting.
- Production identity-provider deployment or production-grade LocalNet security.
- A polished frontend, AP2/x402 support, or a general-purpose treasury platform.

## Decisions

### 1. Separate static authorization from mutable usage

`Mandate` is a static contract containing `owner`, `agent`, `instrumentId`, `expectedAdmin`, `totalCap`, `allowedCounterparties`, and `expiresAt`. `MandateUsage` references its contract ID and contains `spent`.

The owner is signatory and the agent is observer. The owner accepts/creates the authorization and controls `Revoke`; the designated agent alone controls `Charge` on `MandateUsage`. `Charge` fetches the referenced `Mandate`, so archiving it immediately invalidates all later charges. A concurrent charge and revocation conflict through the fetched contract and cannot both commit against inconsistent state.

### 2. Preserve owner authority without giving the agent owner credentials

The owner remains signatory on the authorization and usage contracts. Exercising the authorized choice carries the contract's ledger authorization into its consequences, allowing the Daml workflow to request the constrained transfer. The runtime submits only with `actAs = [agent]`; it never receives `CanActAs(owner)`.

The agent request schema does not contain `sub`, `userId`, `actAs`, `readAs`, owner, sender, instrument, expected administrator, template ID, choice name, or arbitrary command JSON. The adapter obtains its token from its own process configuration, hardcodes the agent party and `MandateUsage_Charge`, and rejects any unknown fields. This prevents the adapter becoming a confused deputy even if the model controls every permitted request value.

### 3. Bind the checked values to the executed transfer

`Charge` accepts only the merchant, amount, and business reference needed for a purchase. Daml asserts:

```daml
assertMsg "amount must be positive" (amount > 0.0)
assertMsg "mandate expired" (now < mandate.expiresAt)
assertMsg "counterparty not allowed" (merchant `elem` mandate.allowedCounterparties)
assertMsg "total cap exceeded" (spent + amount <= mandate.totalCap)
```

The transfer request is then derived in Daml: sender is `owner`, receiver is the checked `merchant`, amount is the checked `amount`, and token/admin identifiers come from `Mandate`. The backend cannot supply alternative policy fields.

### 4. Commit payment, accounting, and receipt atomically

The charge choice calls the Token Standard V1 transfer workflow and accepts only an immediately completed direct transfer. It recreates `MandateUsage` with the new cumulative spend and creates `ChargeReceipt` in the same transaction. A rejected, failed, or pending transfer aborts the complete transaction, leaving spend and receipts unchanged.

Token factory context and selected holding inputs may be supplied as ledger-derived execution inputs, but Daml verifies their instrument/admin identity and derives all material payment fields from the mandate.

### 5. Keep audit truth and attempt logs distinct

`ChargeReceipt` records the mandate reference, owner, agent, merchant, instrument, amount, spend before/after, ledger time, and order/description reference. Receipts prove committed actions. Failed commands do not create ledger events, so the runtime may separately display rejected attempt logs, clearly marked as non-ledger and not mixed with the committed statement.

### 6. Use a narrow runtime surface

The agent-facing adapter exposes `get_mandate`, `charge`, and `statement`. Owner-only revocation is a separate administrative operation. A charge endpoint exercises `MandateUsage_Charge`; it never submits a direct token transfer. Backend validation is for usability only and must not be relied upon for security.

Owner grant/revoke is a separate CLI or process with a separate credential and environment. It is not a hidden route or UI button in the agent service. Tokens are never sent to browser code, LLM context, prompts, logs, receipts, error messages, or source control. Free-text business references are length-limited and escaped when rendered.

### 7. Centralize LocalNet and limit Tailscale exposure

One canonical host runs LocalNet and binds every container port to loopback. The tailnet policy names a dedicated team group and a tagged LocalNet host instead of wildcard destinations. Teammates may access a narrow wallet API and the existing registry gateway; an optional UI may also be exposed. Postgres, participant admin APIs, the Docker socket, and raw Ledger API access for untrusted/AI clients are not exposed. If trusted developers temporarily require raw JSON Ledger API access, it is a separately documented operator grant and never part of the demo security claim. The gateway owns the registry Host-header rewrite, so remote clients use an empty `C8_REGISTRY_HOST` override.

Tailscale proves which tailnet user/device reached a port; it does not grant a Canton party and does not repair a forgeable Ledger API JWT. The application and participant user-rights checks remain mandatory.

### 8. Bind human and application names to canonical ledger identities

Mandates store complete opaque Canton `Party` identifiers, never display names, email addresses, merchant labels, URLs, or application-supplied aliases. A trusted deployment manifest maps friendly names to those party IDs and is shown at confirmation time. Daml checks and the transfer use the same party value; receipts display the full or safely abbreviated party fingerprint so a spoofed label cannot redirect funds.

### 9. Separate holding discovery from spending authority

The agent user cannot read arbitrary owner contracts. If Token Standard settlement requires owner holding contract IDs, a separate resolver with `CanReadAs(owner)` and no `CanActAs` rights returns only compatible holding references and factory context. The charge transaction still validates instrument/admin/owner compatibility in Daml. Compromise of the resolver may leak scoped wallet metadata but cannot authorize a transfer.

### 10. Make charge retries idempotent on-ledger

Every charge has an owner-scoped business reference. The consuming `MandateUsage` successor retains committed references and rejects duplicates. The list is capped at 256 entries; after that the ledger rejects further charges and the owner must rotate to a new mandate. This keeps exact per-mandate replay protection without unbounded contract growth. Ledger command IDs are also stable for transport retries, but backend command deduplication is defense-in-depth rather than the sole replay control.

### 11. Provide two independent kill switches

Mandate `Revoke` is the business-level, on-ledger kill switch and takes effect according to ledger ordering: a charge ordered before revocation may commit, while every charge ordered after it fails. Separately, an operator can deactivate `agent-wallet-user` or revoke its `CanActAs(agent)` right if its credential is compromised. Credential shutdown does not replace mandate revocation.

## Risks / Trade-offs

- LocalNet accepts tokens signed with a known development HMAC secret. Anyone holding it can impersonate any Ledger API user, including an administrator; therefore raw Ledger API access and that secret are trusted-operator surfaces, not part of the adversarial demo boundary.
- The toolkit helper defaults new parties to one shared `ledger-api-user`. Security-sensitive provisioning must always pass an explicit distinct user and then verify exact rights.
- Token Standard interfaces can vary by release. Pin the working toolkit release and prove the integration with a real transfer test early.
- Holding inputs can become stale. Refresh them for each charge and reconcile command status before retrying an unknown result.
- A read-only holdings resolver adds one service boundary. It is preferable to giving the AI `CanReadAs(owner)` or participant-admin access.
- Failed attempts cannot produce an atomic ledger receipt. Preserve command errors separately and label them as runtime evidence.
- A single mutable usage contract serializes charges. This is acceptable for the demo and prevents concurrent overspend.

## Delivery Order

1. Implement the authorization contracts and negative Daml tests.
2. Integrate one direct completed token transfer and prove rollback.
3. Configure parties, rights, and shared LocalNet access.
4. Add the thin wallet adapter and statement query.
5. Wire a deterministic autonomous buyer; add MCP only if time remains.
6. Rehearse the happy path and direct-ledger attacks from clean state.
