# Shared LocalNet identity and access

This runbook implements the agent-wallet demo's development-only boundary:

- owner, agent, and merchant use different ledger users and parties;
- the agent user has `CanActAs(agent)`, never `CanActAs(owner)`;
- Docker publishes LocalNet services on loopback only;
- teammates can reach only the JSON Ledger API on TCP 2975 and the registry
  gateway on TCP 8401 through Tailscale;
- the AI-facing process receives an agent bearer token, not an owner/admin
  token, signing secret, or Docker access.

## 1. Keep LocalNet on loopback

The LocalNet release bundle remains outside this repository. From its
`docker-compose/localnet` directory, set the gateway config to an absolute path
and add this repository's override as the final Compose file:

```bash
export LOCALNET_DIR=$PWD
export IMAGE_TAG=0.6.8
export PARTY_HINT=myteam-dev-1
export APP_PROVIDER_UI_PORT=3001
export LOCALNET_TEAM_GATEWAY_CONFIG=/absolute/path/to/hackathon-toolkit/deployment/localnet-team-gateway.conf

docker compose --env-file "$LOCALNET_DIR/compose.env" \
  --env-file "$LOCALNET_DIR/env/common.env" \
  -f "$LOCALNET_DIR/compose.yaml" \
  -f "$LOCALNET_DIR/resource-constraints.yaml" \
  -f /absolute/path/to/hackathon-toolkit/deployment/localnet-loopback.override.yaml \
  --profile sv --profile app-provider --profile app-user up -d
```

Before continuing, confirm the two intended loopback services answer:

```bash
curl -sS -o /dev/null -w 'ledger %{http_code}\n' http://127.0.0.1:2975/v2/state/ledger-end
curl -sS -o /dev/null -w 'registry %{http_code}\n' http://127.0.0.1:8401/health
```

An unauthenticated `401` from the ledger proves the authenticated API is up.
The registry status can vary by LocalNet release; any HTTP response proves the
gateway route is alive.

## 2. Provision and verify ledger identities

Run this only as the LocalNet operator. It is idempotent: existing matching
parties and users are reused. It grants one `CanActAs` right per user and fails
if it discovers cross-role or broad administrator rights. It deliberately does
not revoke rights automatically.

```bash
python3 agent_wallet_localnet.py --apply
python3 agent_wallet_localnet.py
```

The fixed development identities are:

| Role | Ledger user | Party hint | Expected rights |
|---|---|---|---|
| Owner | `wallet-owner` | `wallet-owner-1` | `CanActAs(owner)` only |
| Agent | `wallet-agent` | `wallet-agent-1` | `CanActAs(agent)` only |
| Merchant | `wallet-merchant` | `wallet-merchant-1` | `CanActAs(merchant)` only |

Party IDs are public identifiers. Tokens and signing secrets are credentials;
do not write them to the repository or the statement/audit output.

## 3. Restrict the tailnet

Merge `deployment/tailscale-policy.example.hujson` into the existing tailnet
policy after replacing the example email addresses. Do not overwrite unrelated
policy. Tag the LocalNet host `tag:agent-wallet-localnet`, preview the policy,
and apply it only after its embedded `accept` and `deny` tests pass.

The grant permits the named team group to reach exactly:

- `tcp:2975` — JSON Ledger API;
- `tcp:8401` — registry gateway.

It does not grant Postgres, Docker, participant/validator admin, gRPC, UI, SSH,
or the other validators' Ledger APIs. A broader pre-existing grant can still
override this boundary; the embedded deny tests are there to catch that.

On the tagged LocalNet host, publish the two loopback listeners to its tailnet
address:

```bash
scripts/configure_tailscale_serve.sh
```

The helper auto-detects the Homebrew userspace daemon at
`~/.tailscale/tailscaled.sock`. For another non-default daemon socket, set
`TAILSCALE_SOCKET` explicitly. It refuses to make changes while any unrelated
Serve listener exists; remove or relocate that listener deliberately, then
rerun the helper.

To remove only these two Serve listeners later (with the same socket
auto-detection):

```bash
scripts/configure_tailscale_serve.sh --remove
```

## 4. Verify from a teammate's machine

This is the meaningful network test: running it on the host would only test
loopback publishing, not tailnet policy.

```bash
python3 scripts/verify_team_access.py localnet-host.example.ts.net
```

It must report the Ledger API's unauthenticated `401`, a successful registry
`/health` response, and every known sensitive LocalNet port blocked. The
tailnet policy's allowlist and embedded tests are the exhaustive access-control
proof; the network probe is a defence-in-depth deployment check. Save its
output with the demo notes as evidence; it contains no secret.

## 5. Launch with the agent-only identity

Mint or obtain a token whose subject is `wallet-agent` outside the AI-facing
process. Give that process only the variables shown in
`deployment/agent.env.example`, then run the preflight in the same environment:

```bash
python3 c8lab.py check
python3 scripts/verify_agent_environment.py
```

`C8_PARTY` must contain the agent's full party ID. In pre-minted token mode,
`c8lab.py check` queries only that party and never switches to the participant
administrator. It also refuses to reuse the token for another `sub`. Do not
provide `C8_JWT_SECRET`, an owner token, a client secret, or access to a Docker
socket.

## Development-only identity warning

Splice LocalNet's `unsafe` HS256 secret is public and shared. Anyone who knows
it can mint a token for `participant_admin`, so neither separate LocalNet users
nor Tailscale turns this demo into a production security boundary. They prove
the intended application permissions and reduce accidental exposure only.

Production must use a real identity provider that issues short-lived tokens
for a fixed subject, map that subject to the `wallet-agent` ledger user, retain
only `CanActAs(agent)`, rotate/revoke credentials, and keep participant
administration on a separate operator path. The agent must never receive a
credential capable of selecting the owner or administrator subject.
