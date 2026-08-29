#!/usr/bin/env python3
"""Fail closed if an AI-facing process receives privileged credentials."""

import base64
import json
import os
from pathlib import Path
import socket
import sys


FORBIDDEN_ENV = {
    "C8_ADMIN_TOKEN",
    "C8_CLIENT_SECRET",
    "C8_JWT_SECRET",
    "C8_OWNER_TOKEN",
    "DOCKER_CERT_PATH",
    "DOCKER_HOST",
    "DOCKER_TLS_VERIFY",
}


def jwt_subject(raw_token):
    try:
        payload = raw_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))["sub"]
    except (IndexError, KeyError, ValueError, json.JSONDecodeError):
        return None


def docker_socket_is_accessible(path):
    if not path.exists():
        return False
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(0.25)
    try:
        client.connect(str(path))
        return True
    except OSError:
        return False
    finally:
        client.close()


def main():
    errors = []
    present = sorted(name for name in FORBIDDEN_ENV if os.environ.get(name))
    if present:
        errors.append("privileged environment variables present: "
                      + ", ".join(present))

    user = os.environ.get("C8_USER")
    party = os.environ.get("C8_PARTY")
    token = os.environ.get("C8_ACCESS_TOKEN")
    if user != "wallet-agent":
        errors.append("C8_USER must be wallet-agent")
    if not party or "::" not in party:
        errors.append("C8_PARTY must be the agent's full party ID")
    if not token:
        errors.append("C8_ACCESS_TOKEN is required")
    elif jwt_subject(token) != user:
        errors.append("C8_ACCESS_TOKEN subject does not match C8_USER")

    sockets = (
        Path("/var/run/docker.sock"),
        Path.home() / ".docker/run/docker.sock",
    )
    exposed = [str(path) for path in sockets if docker_socket_is_accessible(path)]
    if exposed:
        errors.append("Docker socket accessible: " + ", ".join(exposed))

    if errors:
        print("Agent environment verification FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("PASS: agent has its own token and no detected privileged credentials ")
    print("or Docker socket access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
