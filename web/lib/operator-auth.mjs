import { timingSafeEqual } from "node:crypto";

export const MIN_OPERATOR_TOKEN_BYTES = 32;

/**
 * @typedef {"authorized" | "missing-config" | "unauthorized"} OperatorAuthResult
 */

/**
 * Validate the browser-supplied bearer credential without leaking comparison
 * timing. The configured token must be a high-entropy, server-only value.
 *
 * @param {string | null} authorization
 * @param {string | undefined} configuredToken
 * @returns {OperatorAuthResult}
 */
export function authorizeOperator(authorization, configuredToken) {
  if (
    !configuredToken ||
    Buffer.byteLength(configuredToken, "utf8") < MIN_OPERATOR_TOKEN_BYTES
  ) {
    return "missing-config";
  }

  const match = authorization?.match(/^Bearer ([^\s]+)$/i);
  if (!match) return "unauthorized";

  const supplied = Buffer.from(match[1], "utf8");
  const expected = Buffer.from(configuredToken, "utf8");
  if (supplied.length !== expected.length) return "unauthorized";

  return timingSafeEqual(supplied, expected) ? "authorized" : "unauthorized";
}


/**
 * Keep the API credential out of child processes while preserving the other
 * LocalNet and optional planner settings they need.
 *
 * @param {NodeJS.ProcessEnv} environment
 * @returns {NodeJS.ProcessEnv}
 */
export function withoutOperatorToken(environment) {
  const childEnvironment = { ...environment };
  delete childEnvironment.C8_WALLET_OPERATOR_TOKEN;
  return childEnvironment;
}
