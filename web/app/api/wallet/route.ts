import "server-only";

import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 180;

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(process.cwd(), "..");
const cliPath = path.join(repoRoot, "agent_wallet_mvp.py");
const actions = [
  "doctor", "demo", "status", "buy", "statement", "mission", "proof",
] as const;
const maximumBodyBytes = 2_048;

let commandRunning = false;

type Action = (typeof actions)[number];
type RequestBody = {
  action?: unknown;
  amount?: unknown;
  cap?: unknown;
  reference?: unknown;
  goal?: unknown;
};

const decimalPattern = /^(?:0|[1-9]\d*)(?:\.\d{1,10})?$/;
const referencePattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function isAction(value: unknown): value is Action {
  return typeof value === "string" && actions.includes(value as Action);
}

function decimal(value: unknown, label: string): string {
  if (typeof value !== "string" || !decimalPattern.test(value)) {
    throw new Error(`${label} must be a positive decimal with up to 10 places`);
  }
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) {
    throw new Error(`${label} must be greater than zero`);
  }
  return value;
}

function exactKeys(body: RequestBody, allowed: string[]): void {
  const unexpected = Object.keys(body).filter((key) => !allowed.includes(key));
  if (unexpected.length > 0) {
    throw new Error(`unexpected request fields: ${unexpected.join(", ")}`);
  }
}

function commandFor(body: RequestBody): string[] {
  if (!isAction(body.action)) {
    throw new Error(
      "action must be doctor, demo, status, buy, statement, mission, or proof",
    );
  }
  switch (body.action) {
    case "doctor":
    case "status":
    case "statement":
      exactKeys(body, ["action"]);
      return [body.action];
    case "proof":
      exactKeys(body, ["action"]);
      return ["proof", "--json"];
    case "demo": {
      exactKeys(body, ["action", "amount", "cap"]);
      const amount = decimal(body.amount, "amount");
      const cap = decimal(body.cap, "cap");
      if (Number(cap) <= Number(amount)) {
        throw new Error("cap must be greater than the first purchase amount");
      }
      return ["demo", "--amount", amount, "--cap", cap];
    }
    case "buy": {
      exactKeys(body, ["action", "amount", "reference"]);
      const amount = decimal(body.amount, "amount");
      if (typeof body.reference !== "string" || !referencePattern.test(body.reference)) {
        throw new Error(
          "reference must be 1-128 letters, numbers, dots, underscores, colons, or dashes",
        );
      }
      return ["buy", "--amount", amount, "--reference", body.reference];
    }
    case "mission": {
      exactKeys(body, ["action", "goal"]);
      if (typeof body.goal !== "string") {
        throw new Error("goal must be text");
      }
      const goal = body.goal.trim();
      if (!goal || goal.length > 500) {
        throw new Error("goal must be between 1 and 500 characters");
      }
      return ["mission", "--goal", goal, "--json"];
    }
  }
}

type ExecFailure = Error & {
  stdout?: string;
  stderr?: string;
  code?: number | string;
};

export async function POST(request: Request) {
  const started = Date.now();

  const contentType = request.headers.get("content-type")?.toLowerCase() ?? "";
  if (!contentType.startsWith("application/json")) {
    return NextResponse.json(
      { ok: false, error: "Content-Type must be application/json." },
      { status: 415 },
    );
  }

  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (!Number.isFinite(contentLength) || contentLength > maximumBodyBytes) {
    return NextResponse.json(
      { ok: false, error: "Request body is too large." },
      { status: 413 },
    );
  }

  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (origin && host) {
    try {
      if (new URL(origin).host !== host) {
        return NextResponse.json(
          { ok: false, error: "Cross-origin requests are not allowed." },
          { status: 403 },
        );
      }
    } catch {
      return NextResponse.json(
        { ok: false, error: "Invalid request origin." },
        { status: 403 },
      );
    }
  }

  let body: RequestBody;
  let rawBody: string;
  try {
    rawBody = await request.text();
  } catch {
    return NextResponse.json(
      { ok: false, error: "Could not read request body." },
      { status: 400 },
    );
  }

  if (new TextEncoder().encode(rawBody).byteLength > maximumBodyBytes) {
    return NextResponse.json(
      { ok: false, error: "Request body is too large." },
      { status: 413 },
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(rawBody);
  } catch {
    return NextResponse.json(
      { ok: false, error: "Request body must be valid JSON." },
      { status: 400 },
    );
  }

  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return NextResponse.json(
      { ok: false, error: "Request body must be a JSON object." },
      { status: 400 },
    );
  }
  body = parsed as RequestBody;

  let args: string[];
  try {
    args = commandFor(body);
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "invalid request" },
      { status: 400 },
    );
  }

  if (commandRunning) {
    return NextResponse.json(
      { ok: false, error: "Another wallet command is still running." },
      { status: 409 },
    );
  }

  commandRunning = true;

  try {
    const { stdout, stderr } = await execFileAsync("python3", [cliPath, ...args], {
      cwd: repoRoot,
      env: process.env,
      timeout: 170_000,
      maxBuffer: 2 * 1024 * 1024,
    });
    const structured =
      body.action === "mission" || body.action === "proof"
        ? JSON.parse(stdout)
        : undefined;
    return NextResponse.json({
      ok: true,
      action: body.action,
      output: structured ? undefined : stdout.trim(),
      data: structured,
      warning: stderr.trim() || undefined,
      durationMs: Date.now() - started,
    });
  } catch (error) {
    const failure = error as ExecFailure;
    return NextResponse.json(
      {
        ok: false,
        action: body.action,
        output: failure.stdout?.trim() || "",
        error: failure.stderr?.trim() || failure.message,
        durationMs: Date.now() - started,
      },
      { status: 422 },
    );
  } finally {
    commandRunning = false;
  }
}
