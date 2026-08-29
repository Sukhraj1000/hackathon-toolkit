#!/usr/bin/env python3
"""Validate that Tailscale Serve contains only the two LocalNet forwards."""

import argparse
import json
import sys


EXPECTED = {
    "2975": "127.0.0.1:2975",
    "8401": "127.0.0.1:8401",
}


def validate(config, allow_missing=False):
    errors = []
    tcp = config.get("TCP", {})
    unexpected = sorted(set(tcp) - set(EXPECTED))
    if unexpected:
        errors.append("unexpected listener ports: " + ", ".join(unexpected))

    for port, target in EXPECTED.items():
        listener = tcp.get(port)
        if listener is None:
            if not allow_missing:
                errors.append(f"missing tcp/{port}")
            continue
        if listener.get("TCPForward") != target:
            errors.append(
                f"tcp/{port} forwards to {listener.get('TCPForward')!r}, "
                f"expected {target!r}")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-missing", action="store_true",
        help="allow either expected listener to be absent during preflight")
    args = parser.parse_args()
    try:
        config = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid Tailscale Serve JSON: {exc}", file=sys.stderr)
        return 1

    errors = validate(config, allow_missing=args.allow_missing)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
