#!/usr/bin/env python3
"""Run from a teammate's machine to verify the shared LocalNet boundary."""

import argparse
import concurrent.futures
import socket
import sys


ALLOWED_PORTS = (2975, 8401)
FORBIDDEN_PORTS = (
    22, 443, 2000, 2375, 2376,
    2901, 2902, 2903, 3001,
    3901, 3902, 3903, 3975, 4000,
    4901, 4902, 4903, 4975, 5432,
    8443, 9443, 10443,
)


def is_open(host, port, timeout):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


def main():
    parser = argparse.ArgumentParser(
        description="verify the shared LocalNet's teammate-facing endpoints")
    parser.add_argument("host", help="LocalNet host's Tailscale DNS name or IP")
    parser.add_argument("--timeout", type=float, default=1.5)
    args = parser.parse_args()

    ports = ALLOWED_PORTS + FORBIDDEN_PORTS
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ports)) as pool:
        results = dict(zip(
            ports,
            pool.map(lambda port: is_open(args.host, port, args.timeout), ports)))

    failures = []
    for port in ALLOWED_PORTS:
        state = "open" if results[port] else "blocked"
        print(f"required  tcp/{port:<5} {state}")
        if not results[port]:
            failures.append(f"required tcp/{port} is not reachable")
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
    print("\nPASS: only tcp/2975 and tcp/8401 are reachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
