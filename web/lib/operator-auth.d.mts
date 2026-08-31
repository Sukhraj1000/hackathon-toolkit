export const MIN_OPERATOR_TOKEN_BYTES: number;

export type OperatorAuthResult =
  | "authorized"
  | "missing-config"
  | "unauthorized";

export function authorizeOperator(
  authorization: string | null,
  configuredToken: string | undefined,
): OperatorAuthResult;

export function withoutOperatorToken(
  environment: NodeJS.ProcessEnv,
): NodeJS.ProcessEnv;
