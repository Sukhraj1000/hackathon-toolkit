# Agent wallet UI

This Next.js UI is a local operator control surface for the policy-bound Python
wallet. It includes a plain-language Agent Mission, a manual fallback, and a
one-click adversarial/revocation Proof Mode. It does not expose a general shell
endpoint or allow the browser or model to choose a ledger identity, template,
choice, owner credential, canonical merchant, or raw Canton command.

```bash
cd web
npm ci
npm run dev
```

Open `http://127.0.0.1:3000`. LocalNet and the Daml CLI must already be
available. Use **Run doctor**, **Create & run demo**, then **Run autonomous
mission**. The status, mission, manual purchase, and statement controls reuse
the ignored `.c8wallet-state.json` in the repository root. Proof Mode creates
and revokes its own disposable wallet.

The mission uses the deterministic safe planner by default. To enable the
optional OpenAI ranking step, start the server with `OPENAI_API_KEY` set. You
may also set `C8_OPENAI_MODEL`; it defaults to `gpt-5.4-nano`. The key stays in
the Next.js server/Python process and is never sent to the browser.

The API route accepts only seven fixed actions, validates exact request fields,
uses `execFile` without a shell, rejects cross-origin calls, and serializes
wallet commands so two browser actions cannot race over the same holdings.
