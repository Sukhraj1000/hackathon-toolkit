import assert from "node:assert/strict";
import test from "node:test";

import {
  MIN_OPERATOR_TOKEN_BYTES,
  authorizeOperator,
  withoutOperatorToken,
} from "../lib/operator-auth.mjs";

const configuredToken = "a".repeat(MIN_OPERATOR_TOKEN_BYTES);

test("rejects missing or weak server configuration", () => {
  assert.equal(authorizeOperator(null, undefined), "missing-config");
  assert.equal(authorizeOperator(null, "short"), "missing-config");
});

test("rejects missing, malformed, and incorrect bearer credentials", () => {
  assert.equal(authorizeOperator(null, configuredToken), "unauthorized");
  assert.equal(authorizeOperator("Basic abc", configuredToken), "unauthorized");
  assert.equal(authorizeOperator("Bearer wrong", configuredToken), "unauthorized");
});

test("accepts only the exact configured bearer token", () => {
  assert.equal(
    authorizeOperator(`Bearer ${configuredToken}`, configuredToken),
    "authorized",
  );
  assert.equal(
    authorizeOperator(`bearer ${configuredToken}`, configuredToken),
    "authorized",
  );
});

test("removes the operator credential from child-process environments", () => {
  const parent = {
    C8_WALLET_OPERATOR_TOKEN: configuredToken,
    C8_REGISTRY: "http://127.0.0.1:4000",
  };
  const child = withoutOperatorToken(parent);

  assert.equal(child.C8_WALLET_OPERATOR_TOKEN, undefined);
  assert.equal(child.C8_REGISTRY, parent.C8_REGISTRY);
  assert.equal(parent.C8_WALLET_OPERATOR_TOKEN, configuredToken);
});
