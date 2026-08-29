#!/usr/bin/env python3
"""Run from a teammate's machine to verify the shared LocalNet boundary."""

import argparse
import concurrent.futures
import socket
import sys
import urllib.error
import urllib.request


FORBIDDEN_PORTS = (
    22, 443, 2000, 2375, 2376,
    2901, 2902, 2903, 3000, 3001, 3002,
    3901, 3902, 3903, 3975, 4000,
    4901, 4902, 4903, 4975, 5432,
    8080, 8200, 8302, 8400, 8443, 9443, 10443,
)

REQUIRED_HTTP = (
    ("ledger", 2975, "/v2/state/ledger-end", {401}),
    ("registry", 8401, "/health", {200}),
)


def is_open(host, port, timeout):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


def http_status(host, port, path, timeout):
    try:
        with urllib.request.urlopen(
                f"http://{host}:{port}{path}", timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (OSError, TimeoutError, urllib.error.URLError):
        return None


def main():
    parser = argparse.ArgumentParser(
        description="verify the shared LocalNet's teammate-facing endpoints")
    parser.add_argument("host", help="LocalNet host's Tailscale DNS name or IP")
    parser.add_argument("--timeout", type=float, default=1.5)
    args = parser.parse_args()

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(FORBIDDEN_PORTS)) as pool:
        results = dict(zip(
            FORBIDDEN_PORTS,
            pool.map(
                lambda port: is_open(args.host, port, args.timeout),
                FORBIDDEN_PORTS)))

    failures = []
    for name, port, path, expected in REQUIRED_HTTP:
        status = http_status(args.host, port, path, args.timeout)
        display = str(status) if status is not None else "unreachable"
        print(f"required  {name:<8} tcp/{port:<5} HTTP {display}")
        if status not in expected:
            failures.append(
                f"{name} tcp/{port}{path} returned {display}; "
                f"expected {sorted(expected)}")
    for port in FORBIDDEN_PORTS:
        state = "EXPOSED" if results[port] else "blocked"
        print(f"sensitive tcp/{port:<5} {state}")
        if results[port]:
            failures.append(f"sensitive tcp/{port} is reachable")

    if failures:
        print("\nFAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("\nPASS: required services are correct and known sensitive ports are blocked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
