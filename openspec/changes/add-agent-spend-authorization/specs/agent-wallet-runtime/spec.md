# agent-wallet-runtime Specification

## Purpose

Define the least-privilege adapter and shared LocalNet workflow used by an autonomous buyer without moving authorization decisions out of Daml.

## ADDED Requirements

### Requirement: Narrow agent wallet interface

The agent-facing runtime SHALL expose only mandate discovery, authorized charge, and statement operations required for the demo; revocation SHALL remain a separate owner operation.

#### Scenario: Agent buys from an approved merchant

- **WHEN** the autonomous buyer selects an approved offer within the remaining cap
- **THEN** the adapter exercises `MandateUsage.Charge` as the agent party
- **AND** it does not ask for an owner signature at purchase time

#### Scenario: Agent tries to call a general transfer tool

- **WHEN** the AI-facing process requests an operation outside the narrow wallet interface
- **THEN** that operation is unavailable to the process

### Requirement: Backend cannot authorize a forbidden payment

The adapter SHALL treat backend validation as advisory and SHALL rely on the ledger result as the authoritative success or failure.

#### Scenario: Backend checks are removed or bypassed

- **WHEN** a client directly exercises `Charge` with an over-cap, unapproved, expired, or revoked request
- **THEN** the corresponding Daml check rejects the command

### Requirement: Least-privilege party identity

The runtime token SHALL identify a dedicated agent Ledger API user, grant `CanActAs` only for the agent party, and SHALL NOT include owner, any-party, participant-admin, identity-provider-admin, registry administration, or shell credentials.

#### Scenario: Agent token is inspected

- **WHEN** the configured claims and party rights are reviewed
- **THEN** only the intended agent party is available for command submission

#### Scenario: Adapter starts with unexpected rights

- **WHEN** startup rights attestation finds missing or additional rights
- **THEN** the adapter fails closed and serves no charge requests

### Requirement: Safe command-result handling

The adapter SHALL preserve ledger rejection details and SHALL reconcile command state before retrying any submission with an unknown outcome.

#### Scenario: Network response is lost after submission

- **WHEN** the adapter cannot determine whether a charge committed
- **THEN** it queries ledger state using its command or business reference before retrying
- **AND** it does not create a blind duplicate payment

### Requirement: Shared LocalNet access over Tailscale

The canonical LocalNet host SHALL expose the narrow wallet API and registry gateway to an explicit team group and tagged destination, while keeping raw Ledger API and all administrative/data-plane ports private from untrusted and AI clients.

#### Scenario: Teammate uses the adapter remotely

- **WHEN** a teammate connects over Tailscale with the documented endpoints
- **THEN** mandate queries and charge submissions reach the narrow wallet API
- **AND** the registry gateway applies the required Host header

#### Scenario: Remote client probes raw or administrative services

- **WHEN** the client attempts to reach raw Ledger API, Postgres, participant/validator admin APIs, user management, the Docker socket, or shell access through the agent-facing configuration
- **THEN** those services are not exposed

#### Scenario: Trusted development exception is enabled

- **WHEN** named operators need temporary raw Ledger API access
- **THEN** it uses a distinct tailnet grant unavailable to agent and shared-client identities
- **AND** the demo does not present that operator boundary as adversarially secure
