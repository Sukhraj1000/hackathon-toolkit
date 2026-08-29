#!/bin/sh
set -eu

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale CLI is not installed" >&2
  exit 1
fi

tailscale_socket=${TAILSCALE_SOCKET:-}
if [ -z "$tailscale_socket" ] && [ -S "$HOME/.tailscale/tailscaled.sock" ]; then
  tailscale_socket="$HOME/.tailscale/tailscaled.sock"
fi

ts() {
  if [ -n "$tailscale_socket" ]; then
    tailscale --socket="$tailscale_socket" "$@"
  else
    tailscale "$@"
  fi
}

ts status >/dev/null

if [ "${1:-}" = "--remove" ]; then
  ts serve --tcp=2975 off
  ts serve --tcp=8401 off
  ts serve status
  exit 0
fi
if [ "$#" -ne 0 ]; then
  echo "usage: $0 [--remove]" >&2
  exit 2
fi

ts serve --bg --tcp=2975 tcp://127.0.0.1:2975
ts serve --bg --tcp=8401 tcp://127.0.0.1:8401
ts serve status

echo
echo "Only LocalNet's Ledger API (2975) and registry gateway (8401) were added."
