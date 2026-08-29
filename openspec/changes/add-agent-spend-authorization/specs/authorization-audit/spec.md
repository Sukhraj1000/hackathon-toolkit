# authorization-audit Specification

## Purpose

Provide human-readable ledger evidence of every committed agent purchase and identify the exact authorization and policy state that permitted it.

## ADDED Requirements

### Requirement: Receipt for every committed charge

Each successful `Charge` SHALL create one `ChargeReceipt` containing mandate reference, owner, agent, merchant, instrument, amount, spent before, spent after, ledger time, and an order or description reference.

#### Scenario: Authorized charge commits

- **WHEN** an authorized token payment commits
- **THEN** exactly one corresponding receipt is visible to the relevant parties
- **AND** its spent-after value equals spent-before plus amount

#### Scenario: Charge is rejected

- **WHEN** any authorization or token settlement check rejects the transaction
- **THEN** no committed receipt exists for that attempt

### Requirement: Exact authorization linkage

A receipt SHALL reference the immutable mandate contract or stable authorization identifier used by `Charge`.

#### Scenario: Auditor inspects a receipt

- **WHEN** a human opens a completed charge entry
- **THEN** the statement identifies the mandate that allowed the payment
- **AND** displays the merchant's canonical party identifier, amount, token, cumulative spend, and time

### Requirement: Human-readable statement

The runtime SHALL render active or revoked mandate details and committed receipts in chronological order without treating backend state as ledger truth.

#### Scenario: Statement is requested after purchases

- **WHEN** a user requests the wallet statement
- **THEN** it is reconstructed from ledger contracts and transactions
- **AND** its total committed spend agrees with the current or terminal mandate usage

### Requirement: Rejected attempts are clearly separated

Runtime command errors MAY be displayed as rejected attempts but SHALL be labelled as non-ledger attempt logs and SHALL NOT be mixed with committed receipts.

#### Scenario: Overspend attempt is shown in the demo

- **WHEN** an over-cap command is rejected by the ledger
- **THEN** the UI or CLI may display its ledger error as a rejected attempt
- **AND** the committed statement remains unchanged

### Requirement: Audit text is untrusted display data

Merchant labels, descriptions, business references, and ledger error text SHALL be length-limited and safely escaped before display.

#### Scenario: Agent submits active content in a reference

- **WHEN** a business reference contains markup, script syntax, terminal control characters, or an oversized value
- **THEN** the statement renders a bounded inert representation
- **AND** no browser script or terminal control sequence is executed
