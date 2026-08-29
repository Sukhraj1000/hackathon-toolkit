# Security Review: Agent Spend Authorization

## Verdict

The planned Daml capability can strongly prevent a malicious agent from impersonating the owner or redirecting owner funds, provided the runtime identity and network rules below are implemented exactly.

The current LocalNet helper is intentionally unsafe authentication. It uses a known shared HMAC secret, lets code choose the JWT subject, creates tokens without expiry, and defaults allocated parties to one shared Ledger API user. Raw LocalNet Ledger API access therefore cannot be exposed to the AI or treated as an adversarial boundary.

No design is literally unbreakable. The defensible claim is:

> A caller controlling the AI and every allowed wallet request field, and holding only the agent application identity, cannot act as the owner, change the mandate, pay an unapproved party, exceed/replay the cap, or pay after ledger-ordered revocation. Compromise of owner/operator credentials, participant administration, host root, package governance, or the LocalNet signing secret is outside this claim.

## Recommended Demo Topology

```text
AI / deterministic buyer
  |
  | only get_mandate, charge, statement
  v
Narrow wallet adapter (agent identity fixed; strict schema)
  |
  | loopback/private network, actAs=[agent]
  v
Canton JSON Ledger API
  |
  +--> Daml MandateUsage.Charge
         |
         +--> fetch immutable Mandate
         +--> assert amount/cap/party/expiry/idempotency
         +--> constrained Token Standard transfer
         +--> usage successor + receipt atomically

Owner CLI (separate process/token) ------> grant / Revoke only
Read-only resolver (separate user) ------> owner holding references only
Trusted operator terminal --------------> provisioning and direct attack tests
```

The agent execution environment has no route to raw Ledger API, shell, Docker, administrative APIs, owner CLI, token minting code, or the LocalNet JWT signing secret.

## Security Invariants

1. **Authenticated application identity:** every request reaches Canton under one fixed Ledger API user determined by a verified bearer token, never by request data.
2. **Exact party authority:** agent user has only `CanActAs(agent)`; owner user has only `CanActAs(owner)`; resolver has only `CanReadAs(owner)`.
3. **No broad runtime rights:** no runtime user has any-party, participant-admin, or identity-provider-admin rights.
4. **Daml authority:** owner is signatory on static mandate and mutable usage; agent is observer and sole `Charge` controller; owner alone controls `Revoke`.
5. **Delegated consequences:** owner signatory authority on the exercised usage contract and the agent actor authorize only the Daml-defined consequences. This is the mechanism that permits the nested owner transfer without submitting as owner.
6. **Immutable policy:** agent cannot change owner, agent, cap, expiry, allow-list, token, or expected admin.
7. **Canonical identities:** full Canton Party IDs and token/admin IDs are stored and compared; display names never authorize.
8. **Checked equals executed:** sender, receiver, amount, token, and admin in settlement are derived from values checked by Daml.
9. **Atomicity:** payment, usage successor, idempotency marker, and receipt all commit or all roll back.
10. **At-most-once business action:** an active ledger uniqueness marker prevents a duplicate mandate/business reference from paying twice.
11. **Ledger-order revocation:** a charge ordered after archive of the static mandate fails its fetch; a charge already ordered before revoke may commit.
12. **Auditable output:** committed receipts are ledger truth; rejected attempts are separately labelled runtime evidence.

## Findings and Required Controls

| Severity | Finding | Why it matters | Required control |
|---|---|---|---|
| Critical | Known LocalNet HMAC signing secret and caller-selected JWT `sub` | A holder can impersonate any Ledger API user, including participant admin | Never expose minting code/secret or raw Ledger API to AI/judges; use trusted operator boundary; replace with external asymmetric IdP in production |
| Critical | `allocate_party(..., grant_to=ledger-api-user)` default | Naive provisioning gives one user owner, agent, and merchant authority | Always create distinct users and pass explicit `grant_to`; query exact rights afterward |
| Critical | Raw JSON Ledger API also exposes user-management operations | With an admin identity, a caller can grant itself owner rights without participant-admin port access | Keep raw Ledger API private from AI/shared clients; narrow adapter exposes no user management |
| Critical | Adapter could become a confused deputy | Accepting `actAs`, `userId`, template, choice, sender, or generic JSON lets the caller redirect privileged behavior | Strict allow-only schema; fixed token/user/party/template/choice; reject unknown fields |
| Critical | Owner revoke in same service/browser | Prompt injection, endpoint discovery, XSS, or token leakage could invoke owner authority | Separate local owner CLI/process and credential environment; no owner token in browser |
| High | Holding selection appears to require owner visibility | Giving agent `CanReadAs(owner)` exposes unrelated owner contracts and weakens isolation | Separate read-only resolver; no execute rights; Daml revalidates every returned reference |
| High | Backend-only retry handling can double-pay | An unknown result followed by refetch/retry can create a second valid charge | Stable command ID plus on-ledger unique business reference |
| High | Wildcard Tailscale destination rules | Shared users may reach similarly numbered services on unintended devices | Explicit group and tagged destination; exact ports; tailnet policy tests |
| High | Friendly merchant names can be spoofed | A UI/app name is not a Canton identity | Trusted name-to-Party mapping; display fingerprint; Daml allow-list uses the exact transfer receiver |
| High | Package/admin compromise can replace security code | Daml checks only protect the deployed package and participant configuration | Treat DAR deployment and participant admin as trusted operator controls; record deployed package ID |
| Medium | Receipt/reference strings are attacker-controlled | XSS or terminal escape injection can attack the human audit surface | Bound and escape all display text |
| Medium | Revocation described as wall-clock instantaneous | A prior sequenced transaction may commit before revocation | State and test ledger-order semantics precisely |
| Medium | Read and statement filters could over-disclose | A shared backend may return another owner's contracts | Query with the authenticated principal's fixed party and verify stakeholders |

## Authorization Chain Review

### 1. Human/application authentication

Canton Ledger API users are local participant identities. Authentication maps a bearer token to a user ID; user management maps that user to `CanActAs` and `CanReadAs` party rights. The command's `actAs` list must be a subset of the authenticated user's rights.

The adapter must not use a general helper where the caller selects `sub` or `actAs`. It should be constructed with one fixed token provider and one fixed agent party, then attest the resulting user rights before serving.

### 2. Daml authorization

`MandateUsage` must have owner as signatory and agent as observer. `Charge` has agent as controller. In Daml authorization, exercise consequences receive authority from the exercise actors plus the exercised contract's signatories. That gives the nested workflow owner and agent authority without granting the submitting Ledger API user owner rights.

This invariant must be tested with a real Token Standard transfer submitted only as the agent user. If implementation changes the usage signatory/controller structure, repeat the authorization analysis before merging.

### 3. Entity binding

Use complete Party IDs everywhere in policy and settlement. The trusted catalog may attach a friendly label, but the offer's Party ID must equal the configured mapping and the Daml allow-list value. The receipt records the same value.

Pin `InstrumentId` and `expectedAdmin` in the mandate. Validate every supplied holding and factory reference against those values. Never let the registry response silently replace mandate policy.

### 4. Network and process isolation

Loopback container bindings are a good base. The final tailnet grants must target a tagged LocalNet host/service, not `dst: ["*"]`. The AI/shared group reaches only the narrow wallet endpoint. A separate operator group may reach raw Ledger API temporarily for development and judge-directed direct calls.

Tailscale controls network reachability, not Canton party authority. Both layers are required.

### 5. Credential lifecycle

For LocalNet, keep owner/operator operations local, do not provide arbitrary code execution to the AI, and ensure the agent cannot route to raw Ledger API. If an agent credential is suspected compromised, revoke the mandate first, then deactivate the agent user or remove `CanActAs(agent)`.

For production, use a real IdP/JWKS configuration, validate issuer and audience, use short-lived tokens, isolate client credentials, rotate secrets, secure Ledger API transport with TLS, and protect admin APIs separately.

## Mandatory Adversarial Proof

The final test report must include:

1. Agent token with `actAs=[owner]`.
2. Agent token requesting owner grant/revoke.
3. Agent token calling Ledger API user/rights administration.
4. Wrong agent exercising `Charge`.
5. Direct Token Standard owner transfer as agent.
6. Identity-field and arbitrary-command injection into the wallet API.
7. Spoofed approved merchant label with another Party ID.
8. Substituted token, admin, sender, receiver, amount, factory context, and holding.
9. Resolver identity attempting any ledger execution.
10. Below-cap, exact-cap, over-cap, expired, and post-revoke charge.
11. Duplicate business reference and unknown-result retry.
12. Concurrent stale usage and charge/revoke ordering.
13. Tailscale probes for raw Ledger API and all admin/data ports.
14. Rights attestation and secret scan of all AI/browser surfaces.

For every rejection, record the rejecting boundary: network policy, request schema, Ledger API user rights, Daml controller, Daml assertion/fetch, token validation, or contract-key uniqueness.

## Six-Hour Security Gate

Do not spend time on frontend or MCP until all of these are green:

- Exact separate Ledger API users and verified rights.
- Agent-facing process cannot mint tokens or reach raw Ledger API.
- Immutable mandate with cap, allow-list, expiry, revocation, and replay protection.
- Real atomic token transfer.
- Owner CLI isolated from agent service.
- Direct impersonation and bypass tests using the real agent token.
- Statement showing canonical parties and exact mandate authorization.

## Primary References

- Digital Asset, Daml authorization model: https://docs.daml.com/_downloads/DamlEnterprise2.10.2.pdf
- Digital Asset, identity and Ledger API user management: https://docs.digitalasset.com/operate/3.5/howtos/operate/identity_management.html
- Digital Asset, parties and users: https://docs.digitalasset.com/build/3.4/explanations/parties-users.html
- Digital Asset, JSON Ledger API authorization fields: https://docs.digitalasset.com/build/3.4/reference/json-api/openapi.html
- Tailscale grants and least privilege: https://tailscale.com/docs/reference/syntax/grants
