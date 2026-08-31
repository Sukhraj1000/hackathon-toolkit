# spend-authorization Specification

## Purpose

Define the ledger-enforced permission that lets one designated agent spend a bounded amount of one owner's token with approved counterparties until expiry or owner revocation.

## ADDED Requirements

### Requirement: Explicit mandate grant

The system SHALL represent each authorization as a Daml `Mandate` containing a stable owner-issued mandate ID, owner, designated agent, token instrument, expected token administrator, total cap, counterparty allow-list, and expiry.

#### Scenario: Owner grants a mandate

- **WHEN** the owner creates or accepts a mandate with all required policy fields
- **THEN** the ledger creates a mandate visible to the designated agent
- **AND** the agent receives no general authority to act as the owner

#### Scenario: An unrelated party tries to grant owner authority

- **WHEN** a party without owner authority attempts to create or accept the mandate
- **THEN** ledger authorization rejects the transaction

#### Scenario: Agent attempts to alter policy

- **WHEN** the agent attempts to raise the cap, extend expiry, replace the instrument, or change the allowed parties
- **THEN** no such agent-controlled choice exists
- **AND** creating replacement authorization state requires owner authority

### Requirement: Restricted choice authority

The mandate workflow SHALL make the owner the signatory, the designated agent an observer, the designated agent the controller of `Charge`, and the owner the controller of `Revoke`.

#### Scenario: Designated agent requests a charge

- **WHEN** the designated agent exercises `Charge`
- **THEN** the ledger evaluates the mandate policy and payment workflow

#### Scenario: Agent attempts owner-only revocation or mutation

- **WHEN** the agent submits a command requiring owner authority
- **THEN** ledger authorization rejects the command

### Requirement: Ledger-enforced lifetime cap

`Charge` SHALL assert that the amount is positive and cumulative committed spend after the charge does not exceed the total cap.

#### Scenario: Charge is within the remaining cap

- **WHEN** the agent charges a positive amount whose new cumulative spend is at or below the cap
- **THEN** the charge may proceed to token settlement

#### Scenario: Charge exceeds the remaining cap

- **WHEN** the agent charges an amount whose new cumulative spend exceeds the cap
- **THEN** the ledger rejects the complete transaction
- **AND** committed spend remains unchanged

#### Scenario: Concurrent charges would jointly overspend

- **WHEN** concurrent commands consume the same current usage state and together exceed the cap
- **THEN** at most one current usage successor commits
- **AND** no committed ledger state exceeds the cap

### Requirement: Ledger-enforced counterparty allow-list

`Charge` SHALL assert that the receiver is a member of the mandate's allowed counterparties.

#### Scenario: Approved merchant is charged

- **WHEN** the agent selects a merchant present in the allow-list
- **THEN** the charge may proceed to the remaining checks

#### Scenario: Unapproved merchant is charged

- **WHEN** the agent selects a merchant absent from the allow-list
- **THEN** the ledger rejects the complete transaction

### Requirement: Ledger-time expiry

`Charge` SHALL compare ledger time with `expiresAt` and reject a charge at or after expiry.

#### Scenario: Mandate is not expired

- **WHEN** ledger time is earlier than `expiresAt`
- **THEN** the charge may proceed to the remaining checks

#### Scenario: Mandate has expired

- **WHEN** ledger time is equal to or later than `expiresAt`
- **THEN** the ledger rejects the complete transaction

### Requirement: Immediate owner-controlled revocation

The owner SHALL be able to archive the static mandate without agent authorization, and every charge SHALL fetch that mandate before proceeding.

#### Scenario: Owner revokes without agent cooperation

- **WHEN** the owner exercises `Revoke`
- **THEN** the mandate is archived without an agent signature or choice

#### Scenario: Agent charges after revocation

- **WHEN** the agent exercises `Charge` after the referenced mandate was archived
- **THEN** the ledger rejects the transaction because the authorization cannot be fetched

#### Scenario: Charge races with revocation

- **WHEN** a charge and revocation are submitted concurrently
- **THEN** ledger ordering determines which operation commits first
- **AND** no charge ordered after the revocation can commit

### Requirement: Ledger-enforced charge idempotency

Every `Charge` SHALL include a non-empty business reference scoped to one immutable `mandateCid` and SHALL maintain an on-ledger uniqueness marker across that mandate's usage successors. A mandate SHALL accept at most 256 committed references and reject later charges, preserving exact per-mandate-contract replay protection while bounding usage-state growth. `mandateId` SHALL be treated as an operator label rather than a globally unique ledger key; rotation starts a new replay scope, and duplicate active labels SHALL make the adapter fail closed.

#### Scenario: Same purchase is retried

- **WHEN** the same mandate ID and business reference are submitted after the original charge committed
- **THEN** the duplicate charge is rejected on-ledger
- **AND** no second transfer, spend update, or receipt commits

#### Scenario: Transport retry reuses the current command

- **WHEN** a client retries after an unknown network result
- **THEN** it reuses the stable command and business reference
- **AND** the ledger state contains at most one committed purchase for that reference
