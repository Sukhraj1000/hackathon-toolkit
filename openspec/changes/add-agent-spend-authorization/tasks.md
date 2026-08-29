# Tasks: Ledger-enforced agent spend authorization

## 1. Daml authorization core — Person 1

- [ ] 1.1 Implement static `Mandate`, mutable `MandateUsage`, and `ChargeReceipt`; verify template signatories, observers, and choice controllers in Daml tests.
- [ ] 1.2 Implement owner grant/acceptance and owner-only `Revoke`; verify revocation succeeds without agent participation and post-revocation charge fails.
- [ ] 1.3 Add positive amount, total cap, counterparty allow-list, and ledger-time expiry assertions; verify under-cap succeeds and each forbidden case fails in `daml test`.
- [ ] 1.4 Add a stale/concurrent usage test or equivalent transaction-conflict proof; verify no committed state can exceed the cap.
- [ ] 1.5 Remove agent-controlled policy mutation and add an owner-scoped on-ledger idempotency key for `(mandateId, businessReference)`; verify cap/expiry/allow-list/token cannot be changed and a replay cannot pay twice.

## 2. Atomic Token Standard payment — Person 1, supported by Person 2

- [ ] 2.1 Pin and import the working Token Standard V1 interfaces used by LocalNet; verify the Daml package builds from a clean checkout.
- [ ] 2.2 Invoke the direct transfer workflow from `Charge`, deriving sender, receiver, amount, instrument, and expected admin in Daml; verify owner and merchant balances change.
- [ ] 2.3 Reject incompatible factory context, holdings, and any non-completed transfer result; verify no alternative token or payment field can commit.
- [ ] 2.4 Make transfer, usage successor, and receipt one atomic transaction; verify failed settlement leaves balances, spent, and receipts unchanged.

## 3. Identity isolation and shared LocalNet access — Person 2

- [ ] 3.1 Create distinct owner, agent, merchant, read-only resolver, and operator Ledger API users; explicitly allocate/grant each party without the shared helper default and verify their exact rights.
- [ ] 3.2 Add startup rights attestation that rejects extra/missing rights, any-party rights, admin rights, wrong primary party, or a deactivated user; verify the runtime fails closed.
- [ ] 3.3 Replace wildcard tailnet destinations with an explicit team group and tagged LocalNet host; expose only the narrow wallet API/registry to shared clients and verify policy allow/deny tests.
- [ ] 3.4 Keep raw Ledger API, Postgres, participant/validator admin, user management, Docker, shell, owner credentials, and JWT signing material outside the agent-facing network and process; verify each is unreachable or absent.
- [ ] 3.5 If trusted developers need raw Ledger API access, define a separate named-operator grant and document it outside the adversarial boundary; verify the agent/shared identities cannot use it.
- [ ] 3.6 Document that the known LocalNet HMAC secret permits user impersonation and define production OIDC/JWKS, issuer/audience, expiry, and per-service credentials; scan agent/browser/log outputs for secrets.

## 4. Agent wallet adapter — Person 2

- [ ] 4.1 Implement `get_mandate`, `charge`, and `statement` over the JSON Ledger API; hardcode the authenticated user, agent party, template, and choice, and verify `charge` exercises only `MandateUsage.Charge`.
- [ ] 4.2 Keep owner grant/revoke in a separate CLI/process, credential source, and environment; verify the AI-facing service and browser cannot invoke or obtain them.
- [ ] 4.3 Surface ledger errors and add unknown-result reconciliation using command/business references; verify retries cannot blindly duplicate a purchase.
- [ ] 4.4 Bypass any adapter-side checks in an integration test; verify the same forbidden request still fails on the ledger.
- [ ] 4.5 Use a strict request schema that rejects `sub`, `userId`, `actAs`, `readAs`, owner, sender, token/admin, template/choice, and arbitrary-command overrides; verify every injection attempt submits nothing.
- [ ] 4.6 Add a separate holdings resolver with `CanReadAs(owner)` and no execution rights if required by Token Standard input selection; verify it cannot submit a transfer and the agent never receives its credential.

## 5. Autonomous buyer and audit statement — Person 3

- [ ] 5.1 Implement a deterministic agent flow that selects an approved offer and calls the wallet adapter; verify a purchase completes without owner action at charge time.
- [ ] 5.2 Render mandate policy, canonical party identifiers, current status, committed receipts, authorization link, and cumulative spend as a human-readable statement; verify values agree with ledger state.
- [ ] 5.3 Display rejected command evidence separately from committed receipts; verify an over-cap attempt does not change the statement.
- [ ] 5.4 Add an MCP wrapper only if the core demo is green; verify it exposes the same narrow operations and no owner/general-transfer capability.
- [ ] 5.5 Escape and length-limit merchant labels, descriptions, business references, and error output; verify markup and terminal-control payloads render inertly.

## 6. Security proof and demo rehearsal — Person 3, verified by all

- [ ] 6.1 Run under-cap, exact-cap, over-cap, wrong-counterparty, expired, and post-revocation scenarios; verify expected ledger results and unchanged state on every rejection.
- [ ] 6.2 Attempt direct Ledger API bypasses, direct owner token transfer as agent, and substituted token/payment inputs; verify all fail on-ledger.
- [ ] 6.3 Rehearse a clean end-to-end demo: fund owner, grant mandate, autonomous purchase, statement, attack attempts, revoke, and final failed charge.
- [ ] 6.4 Record the exact Daml assertion/controller/fetch lines used to explain cap, allow-list, expiry, and revocation to judges; verify they match the deployed DAR.
- [ ] 6.5 Run the full Daml and integration test suites from a clean state and save concise commands/results in the README or demo runbook.
- [ ] 6.6 With real Ledger API users/tokens, attempt owner `actAs`, owner revoke/grant, rights administration, wrong-agent charge, spoofed merchant party, resolver execution, and every identity-field injection; verify the expected boundary rejects each.
- [ ] 6.7 Inspect all runtime user rights and scan environment, process arguments, logs, browser assets, prompts, and errors for owner/admin/signing secrets; verify no privileged material crosses into the AI surface.
- [ ] 6.8 Retry a committed business reference, submit stale usage, and race charge with revoke; verify at-most-once payment and ledger-order revocation semantics.
