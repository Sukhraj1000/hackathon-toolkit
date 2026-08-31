#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n== Python syntax and unit tests ==\n'
cd "$repo_root"
python3 -m compileall -q canton8_agent agent_wallet_mvp.py agent_wallet_localnet.py c8lab.py
python3 -m unittest discover -s tests -v

if command -v daml >/dev/null 2>&1 && java -version >/dev/null 2>&1; then
  printf '\n== Daml build and script tests ==\n'
  (cd "$repo_root/daml-starter" && daml build)
  (cd "$repo_root/daml-starter-test" && daml test)
else
  printf '\n== Daml checks skipped (put Daml and Java on PATH to enable) ==\n'
fi

printf '\n== Web install, authentication tests, typecheck and production build ==\n'
cd "$repo_root/web"
npm ci --no-audit --no-fund
npm test
npm run typecheck
npm run build

printf '\nAll offline checks passed.\n'
printf 'For the real ledger demo, start LocalNet and run: python3 agent_wallet_mvp.py doctor\n'
