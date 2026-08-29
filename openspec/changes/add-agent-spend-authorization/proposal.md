# Change: Add ledger-enforced agent spend authorization

## Why

Giving an AI agent a hot owner key gives it unlimited authority if it malfunctions or is manipulated. The wallet needs a narrow, revocable authorization whose cap, counterparty list, expiry, and payment effects are enforced atomically by Daml on Canton.

## What Changes

- Add a static `Mandate` describing the owner, agent, token, total cap, allowed counterparties, and expiry.
- Add mutable `MandateUsage` that records cumulative committed spend while preserving owner authorization over funds.
- Let only the designated agent request a charge and only the owner revoke the mandate.
- Execute a Token Standard V1 payment, spend update, and audit receipt in one ledger transaction.
- Add a thin wallet adapter and human-readable statement; neither may weaken or replace Daml checks.
- Run the shared demo on one LocalNet host, with narrowly scoped Ledger API and registry access over Tailscale.

## Capabilities

### New Capabilities

- `spend-authorization`: Ledger-enforced creation, use, limits, expiry, allow-listing, and revocation of agent mandates.
- `authorized-token-payment`: Atomic Token Standard V1 payment whose material fields are derived from the mandate and checked charge.
- `authorization-audit`: Human-readable committed receipts linked to the exact permission used.
- `agent-wallet-runtime`: Least-privilege adapter, statement, and shared LocalNet demo workflow.
- `principal-identity-isolation`: End-to-end binding from authenticated application identity to one Canton ledger user, one permitted party role, and a narrow operation set.

### Modified Capabilities

- None.

## Impact

- Daml: new or revised mandate, usage, receipt, and Token Standard integration modules and tests.
- Runtime: Python wallet adapter or MCP wrapper over the JSON Ledger API.
- Infrastructure: shared LocalNet party allocation, Tailscale access, and registry gateway configuration.
- Dependencies: pin compatible Token Standard V1 DARs and interfaces already used by the toolkit.
- Security: the agent acts only as its own party; owner credentials and LocalNet administrative secrets remain outside the agent process.
- Network boundary: untrusted callers reach only the narrow wallet API; raw Ledger API access remains a trusted-development/operator surface while LocalNet uses forgeable development JWTs.
