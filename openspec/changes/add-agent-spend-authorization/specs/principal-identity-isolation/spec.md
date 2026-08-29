# principal-identity-isolation Specification

## Purpose

Prevent a person, AI process, merchant application, or network peer from impersonating an owner or another application across the authentication-to-ledger authorization chain.

## ADDED Requirements

### Requirement: One runtime principal maps to one ledger role

The deployment SHALL create distinct Ledger API users for owner administration, agent execution, merchant operation, read-only holding resolution, and participant administration. It SHALL grant each user exactly the rights required by its role.

#### Scenario: Agent user rights are inspected

- **WHEN** the deployment queries the Ledger API rights for `agent-wallet-user`
- **THEN** the only act right is `CanActAs(agent)`
- **AND** it has no owner, merchant, any-party, participant-admin, or identity-provider-admin right

#### Scenario: Owner and agent parties are provisioned

- **WHEN** the owner, agent, and merchant parties are allocated
- **THEN** each party is granted to an explicitly named distinct user
- **AND** provisioning does not rely on the helper's shared default user

#### Scenario: Runtime has extra rights

- **WHEN** startup attestation finds an unexpected right, primary party, user identity, or deactivated state
- **THEN** the affected runtime fails closed before serving requests

### Requirement: Request data cannot select ledger identity

The agent adapter SHALL derive its authenticated user, `actAs` party, template, choice, owner, sender, instrument, and expected administrator from trusted configuration and ledger contracts, not from model-controlled request fields.

#### Scenario: Caller supplies identity override fields

- **WHEN** a request contains `sub`, `userId`, `actAs`, `readAs`, owner, sender, template ID, choice name, instrument, expected administrator, or arbitrary command JSON
- **THEN** schema validation rejects the request
- **AND** no ledger command is submitted

#### Scenario: Caller invokes the Ledger API with the agent token

- **WHEN** the caller sets `actAs` to the owner or another party
- **THEN** Ledger API user-rights authorization rejects the command

### Requirement: Owner operations use an isolated credential boundary

Owner grant and revoke operations SHALL run in a separate CLI or process with a separate token source and environment from the agent service.

#### Scenario: Agent requests owner revocation

- **WHEN** the AI-facing service is asked to invoke `Revoke`, grant a mandate, manage users, or grant rights
- **THEN** the operation is unavailable
- **AND** the agent process has no credential capable of performing it

#### Scenario: Browser loads the demo UI

- **WHEN** the UI is rendered or inspected
- **THEN** no owner, participant-admin, identity-provider-admin, or JWT-signing secret is present in browser code, storage, network responses, or source maps

### Requirement: Canonical party identifiers bind entity identity

Mandates, charges, transfers, and receipts SHALL use complete opaque Canton `Party` values. Friendly names SHALL come only from a trusted deployment mapping and SHALL NOT determine the receiver.

#### Scenario: Merchant label is spoofed

- **WHEN** an offer uses an approved merchant's display name but supplies a different party ID
- **THEN** the trusted mapping detects a mismatch or Daml rejects the unapproved party
- **AND** payment cannot be redirected to the spoofing party

#### Scenario: Human reviews a merchant

- **WHEN** a merchant is shown in mandate or receipt output
- **THEN** the output includes its canonical party identifier or recognizable fingerprint
- **AND** the same party value is used by the allow-list check and transfer

### Requirement: Raw administrative surfaces stay outside the adversarial boundary

The canonical host SHALL bind LocalNet services to loopback and SHALL expose only explicitly required application endpoints to the team tailnet. Untrusted/AI callers SHALL NOT receive raw Ledger API, participant admin, validator admin, database, Docker, shell, or user-management access.

#### Scenario: Agent reaches the shared host

- **WHEN** the agent connects using its allowed network identity
- **THEN** it can reach only the narrow wallet API required for its role
- **AND** it cannot reach raw Ledger API or administrative ports

#### Scenario: Trusted developer needs raw Ledger API access

- **WHEN** temporary direct development access is enabled
- **THEN** it is limited to a named trusted-operator group and tagged LocalNet destination
- **AND** it is documented as outside the security demo claim

#### Scenario: Tailnet policy is reviewed

- **WHEN** grants affecting the LocalNet host are enumerated
- **THEN** no team or shared-client rule uses a wildcard destination or wildcard port
- **AND** policy tests prove allowed and denied port combinations

### Requirement: LocalNet signing material is contained

While LocalNet uses the development HMAC authenticator, its signing secret and participant-admin identity SHALL remain only in trusted operator tooling and SHALL NOT be available to the agent, browser, MCP server, public repository output, logs, or judge-facing environment.

#### Scenario: Agent environment and output are scanned

- **WHEN** environment variables, process arguments, logs, prompts, error responses, and browser bundles are inspected
- **THEN** no LocalNet signing secret, owner token, or administrator token is present

#### Scenario: Production deployment is designed

- **WHEN** the system moves beyond the trusted LocalNet demo
- **THEN** it uses an external identity provider with asymmetric signature verification, issuer and audience validation, short-lived tokens, and distinct service credentials
- **AND** it does not use the shared HMAC development authenticator

### Requirement: Holding discovery cannot authorize spending

If owner holding references are required to build the Token Standard transaction, they SHALL be obtained by a resolver with `CanReadAs(owner)` and no owner or any-party execution rights. The agent SHALL NOT receive the resolver credential.

#### Scenario: Resolver credential is used to submit a transfer

- **WHEN** the resolver user submits a command requiring owner authority
- **THEN** Ledger API authorization rejects the command

#### Scenario: Agent builds a charge

- **WHEN** compatible holding references are needed
- **THEN** the resolver returns only scoped execution references
- **AND** Daml independently verifies owner, instrument, and administrator compatibility before settlement

### Requirement: Credential compromise has an operational kill switch

The operator SHALL be able to deactivate the agent Ledger API user or revoke its `CanActAs(agent)` right independently of mandate revocation.

#### Scenario: Agent credential is suspected compromised

- **WHEN** the operator deactivates the user or removes its act right
- **THEN** later Ledger API submissions using that user fail
- **AND** existing mandate contracts remain auditable

### Requirement: Authentication is tested through the real Ledger API

Identity-isolation tests SHALL use deployed Ledger API users and bearer tokens in addition to Daml Script authorization tests.

#### Scenario: Test suite validates impersonation resistance

- **WHEN** integration tests run against the demo participant
- **THEN** they attempt owner `actAs`, owner revocation, user-rights administration, direct owner transfer, wrong-agent charge, spoofed merchant party, resolver execution, and identity-field injection
- **AND** each attempt fails at the intended network, schema, Ledger API rights, or Daml boundary
- **AND** the test report identifies which boundary produced each rejection
