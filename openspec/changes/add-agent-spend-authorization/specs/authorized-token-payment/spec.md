# authorized-token-payment Specification

## Purpose

Define how an approved charge moves real Token Standard V1 value while binding every material transfer field to the permission checked by Daml.

## ADDED Requirements

### Requirement: Real direct token settlement

An approved `Charge` SHALL invoke the pinned Token Standard V1 transfer workflow and SHALL accept only a direct transfer that completes in the same ledger transaction.

#### Scenario: Approved payment completes

- **WHEN** all mandate checks pass and valid owner holdings cover the charge
- **THEN** the owner's token balance decreases by the charged amount
- **AND** the approved merchant's token balance increases by the charged amount

#### Scenario: Transfer remains pending or fails

- **WHEN** the token workflow does not return the required completed result
- **THEN** the ledger rejects the complete charge transaction

### Requirement: Checked values equal executed values

Daml SHALL derive the sender from the mandate owner, receiver from the checked merchant, amount from the checked charge amount, and instrument/admin identifiers from the mandate.

#### Scenario: Backend attempts to substitute payment fields

- **WHEN** a client supplies execution inputs referring to another sender, receiver, amount, instrument, or administrator
- **THEN** Daml rejects them or ignores them in favor of the mandate-derived values
- **AND** no substituted transfer commits

### Requirement: Execution inputs are validated

Daml SHALL validate that supplied token factory context and owner holding inputs are compatible with the mandate's pinned instrument and expected administrator.

#### Scenario: Input holding belongs to another instrument

- **WHEN** a client supplies a holding that does not match the mandate instrument
- **THEN** the ledger rejects the charge

### Requirement: Atomic payment and allowance accounting

The token transfer, updated cumulative spend, and charge receipt SHALL commit atomically or not at all.

#### Scenario: Token transfer fails after authorization checks

- **WHEN** token settlement fails for insufficient holdings or another ledger reason
- **THEN** no successor usage contract is committed
- **AND** no charge receipt is committed
- **AND** the previous spend value remains effective

### Requirement: Direct owner transfer remains unavailable to the agent

The deployed party rights SHALL NOT grant the agent `CanActAs(owner)`, so the agent cannot bypass `Charge` by submitting a direct transfer from owner holdings.

#### Scenario: Agent submits a direct owner transfer

- **WHEN** the agent identity submits a Token Standard transfer that requires owner authority
- **THEN** ledger authorization rejects the command
