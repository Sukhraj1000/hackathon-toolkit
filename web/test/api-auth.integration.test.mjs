import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const nextBin = path.join(webRoot, "node_modules", "next", "dist", "bin", "next");
const configuredToken = "a".repeat(32);

async function unusedPort() {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close((error) => error ? reject(error) : resolve(port));
    });
  });
}

async function startServer({ token, shimDirectory, marker }) {
  const port = await unusedPort();
  const environment = {
    ...process.env,
    C8_TEST_EXEC_MARKER: marker,
    PATH: `${shimDirectory}${path.delimiter}${process.env.PATH ?? ""}`,
  };
  if (token === undefined) {
    delete environment.C8_WALLET_OPERATOR_TOKEN;
  } else {
    environment.C8_WALLET_OPERATOR_TOKEN = token;
  }

  const child = spawn(
    process.execPath,
    [nextBin, "start", "--hostname", "127.0.0.1", "--port", String(port)],
    { cwd: webRoot, env: environment, stdio: ["ignore", "pipe", "pipe"] },
  );
  let output = "";
  const capture = (chunk) => {
    output = `${output}${chunk.toString()}`.slice(-8_000);
  };
  child.stdout.on("data", capture);
  child.stderr.on("data", capture);

  const baseUrl = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`Next.js exited before readiness:\n${output}`);
    }
    try {
      const response = await fetch(baseUrl);
      if (response.ok) {
        return {
          baseUrl,
          async stop() {
            if (child.exitCode !== null) return;
            await new Promise((resolve) => {
              const timer = setTimeout(() => {
                if (child.exitCode === null) child.kill("SIGKILL");
                resolve();
              }, 5_000);
              child.once("exit", () => {
                clearTimeout(timer);
                resolve();
              });
              child.kill("SIGTERM");
            });
          },
        };
      }
    } catch {
      // Retry until the bounded readiness deadline.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  child.kill("SIGKILL");
  throw new Error(`Next.js did not become ready:\n${output}`);
}

async function post(baseUrl, token, body = { action: "doctor" }) {
  const headers = { "Content-Type": "application/json" };
  if (token !== undefined) headers.Authorization = `Bearer ${token}`;
  return await fetch(`${baseUrl}/api/wallet`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

test("wallet API rejects unauthenticated requests before process execution", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "wallet-api-auth-"));
  const marker = path.join(directory, "python-executed");
  const shim = path.join(directory, "python3");
  await writeFile(
    shim,
    "#!/bin/sh\n: > \"$C8_TEST_EXEC_MARKER\"\nprintf 'unexpected execution\\n'\n",
  );
  await chmod(shim, 0o755);

  let server;
  try {
    server = await startServer({ shimDirectory: directory, marker });
    const missingConfiguration = await post(server.baseUrl);
    assert.equal(missingConfiguration.status, 503);
    assert.equal(existsSync(marker), false);
    await server.stop();
    server = undefined;

    server = await startServer({
      token: configuredToken,
      shimDirectory: directory,
      marker,
    });
    const missingCredential = await post(server.baseUrl);
    assert.equal(missingCredential.status, 401);
    assert.match(
      missingCredential.headers.get("www-authenticate") ?? "",
      /^Bearer /,
    );

    const wrongCredential = await post(server.baseUrl, "b".repeat(32));
    assert.equal(wrongCredential.status, 401);

    const acceptedCredential = await post(
      server.baseUrl,
      configuredToken,
      { action: "not-an-action" },
    );
    assert.equal(acceptedCredential.status, 400);
    assert.equal(existsSync(marker), false);
  } finally {
    if (server) await server.stop();
    await rm(directory, { recursive: true, force: true });
  }
});
