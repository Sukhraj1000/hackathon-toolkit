# Agent wallet UI

This Next.js UI is a local control surface for the fixed Python MVP commands.
It does not expose a general shell endpoint or allow the browser to choose a
ledger identity, template, choice, owner credential, or raw Canton command.

```bash
cd web
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. LocalNet and the Daml CLI must already be
available. Use **Run doctor**, then **Create & run demo**. The status, purchase,
and statement controls reuse the ignored `.c8wallet-state.json` in the
repository root.
