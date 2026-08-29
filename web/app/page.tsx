"use client";

import { FormEvent, useMemo, useState } from "react";

type Action = "doctor" | "demo" | "status" | "buy" | "statement";
type ApiResponse = {
  ok: boolean;
  action?: Action;
  output?: string;
  warning?: string;
  error?: string;
  durationMs?: number;
};
type Activity = ApiResponse & { id: number; at: string };

const actionLabels: Record<Action, string> = {
  doctor: "Environment doctor",
  demo: "Create demo wallet",
  status: "Refresh mandate",
  buy: "Purchase",
  statement: "Load statement",
};

function field(output: string, label: string): string {
  const line = output
    .split("\n")
    .find((candidate) => candidate.trimStart().startsWith(label));
  if (!line) return "—";
  return line.slice(label.length).trim() || "—";
}

function short(value: string): string {
  if (value === "—" || value.length <= 20) return value;
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

export default function WalletDashboard() {
  const [running, setRunning] = useState<Action | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [latestOutput, setLatestOutput] = useState(
    "Run Doctor to verify LocalNet, then create a demo wallet.",
  );
  const [statusOutput, setStatusOutput] = useState("");
  const [statementOutput, setStatementOutput] = useState("");
  const [demoAmount, setDemoAmount] = useState("0.1");
  const [demoCap, setDemoCap] = useState("1.0");
  const [buyAmount, setBuyAmount] = useState("0.05");
  const [reference, setReference] = useState("ui-order-001");

  const run = async (action: Action, values: Record<string, string> = {}) => {
    setRunning(action);
    let result: ApiResponse;
    try {
      const response = await fetch("/api/wallet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...values }),
      });
      result = (await response.json()) as ApiResponse;
    } catch (error) {
      result = {
        ok: false,
        action,
        error: error instanceof Error ? error.message : "Request failed",
      };
    }

    const output = result.output || result.error || "No output returned";
    setLatestOutput(output);
    if (result.ok && action === "status") setStatusOutput(result.output || "");
    if (result.ok && action === "statement") {
      setStatementOutput(result.output || "");
    }
    setActivity((current) => [
      {
        ...result,
        action,
        id: Date.now(),
        at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
      ...current,
    ].slice(0, 8));
    setRunning(null);
    return result;
  };

  const handleDemo = async (event: FormEvent) => {
    event.preventDefault();
    const result = await run("demo", { amount: demoAmount, cap: demoCap });
    if (result.ok) {
      await run("status");
      await run("statement");
    }
  };

  const handleBuy = async (event: FormEvent) => {
    event.preventDefault();
    const result = await run("buy", { amount: buyAmount, reference });
    if (result.ok) {
      setReference(`ui-order-${String(Date.now()).slice(-6)}`);
      await run("status");
      await run("statement");
    }
  };

  const handleRefresh = async () => {
    const result = await run("status");
    if (result.ok) await run("statement");
  };

  const metrics = useMemo(() => ({
    status: field(statusOutput, "status"),
    mandate: short(field(statusOutput, "mandate")),
    allowance: field(statusOutput, "allowance"),
    remaining: field(statusOutput, "remaining"),
    receipts: field(statementOutput, "receipts"),
  }), [statusOutput, statementOutput]);

  const busy = running !== null;

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brandMark">C8</span>
          <div>
            <strong>Agent Wallet</strong>
            <span>LocalNet control surface</span>
          </div>
        </div>
        <div className="networkPill">
          <span className="pulse" /> LocalNet sandbox
        </div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">POLICY-BOUND PAYMENTS</p>
          <h1>Test the wallet from intent to ledger receipt.</h1>
          <p className="heroCopy">
            Provision a mandate, execute constrained purchases, and inspect the
            resulting ledger evidence—without exposing owner authority.
          </p>
        </div>
        <button
          className="button buttonSecondary doctorButton"
          disabled={busy}
          onClick={() => run("doctor")}
        >
          <span className="buttonIcon">+</span>
          {running === "doctor" ? "Checking…" : "Run doctor"}
        </button>
      </section>

      <section className="metrics" aria-label="Wallet metrics">
        <article className="metric metricPrimary">
          <span>Mandate status</span>
          <strong className={metrics.status === "active" ? "activeText" : ""}>
            {metrics.status}
          </strong>
          <small>{metrics.mandate}</small>
        </article>
        <article className="metric">
          <span>Allowance</span>
          <strong>{metrics.allowance}</strong>
          <small>Ledger-enforced cap</small>
        </article>
        <article className="metric">
          <span>Remaining</span>
          <strong>{metrics.remaining}</strong>
          <small>Available to the agent</small>
        </article>
        <article className="metric">
          <span>Receipts</span>
          <strong>{metrics.receipts}</strong>
          <small>Committed purchases</small>
        </article>
      </section>

      <div className="workspace">
        <section className="actionColumn">
          <div className="sectionHeading">
            <div>
              <p className="eyebrow">CONTROL PANEL</p>
              <h2>Wallet actions</h2>
            </div>
            <button
              className="textButton"
              disabled={busy}
              onClick={handleRefresh}
            >
              {running === "status" || running === "statement" ? "Refreshing…" : "Refresh status"}
            </button>
          </div>

          <form className="actionCard" onSubmit={handleDemo}>
            <div className="stepNumber">01</div>
            <div className="actionBody">
              <div className="actionTitle">
                <div>
                  <h3>Create demo wallet</h3>
                  <p>Fresh identities, mandate, funding, and first purchase.</p>
                </div>
                <span className="tag">Setup</span>
              </div>
              <div className="inputRow">
                <label>
                  First purchase
                  <div className="inputWithUnit">
                    <input
                      inputMode="decimal"
                      value={demoAmount}
                      onChange={(event) => setDemoAmount(event.target.value)}
                    />
                    <span>Amulet</span>
                  </div>
                </label>
                <label>
                  Total cap
                  <div className="inputWithUnit">
                    <input
                      inputMode="decimal"
                      value={demoCap}
                      onChange={(event) => setDemoCap(event.target.value)}
                    />
                    <span>Amulet</span>
                  </div>
                </label>
              </div>
              <button className="button buttonPrimary" disabled={busy} type="submit">
                {running === "demo" ? "Provisioning wallet…" : "Create & run demo"}
              </button>
            </div>
          </form>

          <form className="actionCard" onSubmit={handleBuy}>
            <div className="stepNumber">02</div>
            <div className="actionBody">
              <div className="actionTitle">
                <div>
                  <h3>Make a purchase</h3>
                  <p>Charge the configured merchant through the active mandate.</p>
                </div>
                <span className="tag tagAccent">Live</span>
              </div>
              <div className="inputRow purchaseInputs">
                <label>
                  Amount
                  <div className="inputWithUnit">
                    <input
                      inputMode="decimal"
                      value={buyAmount}
                      onChange={(event) => setBuyAmount(event.target.value)}
                    />
                    <span>Amulet</span>
                  </div>
                </label>
                <label className="referenceField">
                  Business reference
                  <input
                    value={reference}
                    maxLength={128}
                    pattern="[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
                    onChange={(event) => setReference(event.target.value)}
                  />
                </label>
              </div>
              <button className="button buttonPrimary" disabled={busy} type="submit">
                {running === "buy" ? "Submitting charge…" : "Submit purchase"}
              </button>
            </div>
          </form>

          <div className="actionCard compactCard">
            <div className="stepNumber">03</div>
            <div className="actionBody auditBody">
              <div>
                <h3>Inspect ledger evidence</h3>
                <p>Read the chronological receipt statement from Canton.</p>
              </div>
              <button
                className="button buttonSecondary"
                disabled={busy}
                onClick={() => run("statement")}
              >
                {running === "statement" ? "Loading…" : "View statement"}
              </button>
            </div>
          </div>
        </section>

        <aside className="evidenceColumn">
          <section className="consoleCard">
            <div className="consoleHeader">
              <div>
                <span className="consoleDot red" />
                <span className="consoleDot amber" />
                <span className="consoleDot green" />
              </div>
              <span>{running ? `${actionLabels[running]} running` : "CLI output"}</span>
            </div>
            <pre aria-live="polite">{latestOutput}</pre>
          </section>

          <section className="activityCard">
            <div className="sectionHeading compactHeading">
              <div>
                <p className="eyebrow">SESSION</p>
                <h2>Recent activity</h2>
              </div>
            </div>
            <div className="activityList">
              {activity.length === 0 ? (
                <p className="emptyState">No commands run in this browser session.</p>
              ) : activity.map((item) => (
                <div className="activityItem" key={item.id}>
                  <span className={item.ok ? "statusIcon ok" : "statusIcon failed"}>
                    {item.ok ? "✓" : "!"}
                  </span>
                  <div>
                    <strong>{actionLabels[item.action || "doctor"]}</strong>
                    <span>
                      {item.ok ? "Completed" : "Needs attention"}
                      {item.durationMs ? ` · ${(item.durationMs / 1000).toFixed(1)}s` : ""}
                    </span>
                  </div>
                  <time>{item.at}</time>
                </div>
              ))}
            </div>
          </section>

          <section className="boundaryNote">
            <span className="lockIcon">◆</span>
            <div>
              <strong>Constrained by design</strong>
              <p>
                The UI cannot choose a ledger user, owner identity, template,
                choice, or raw command. Daml remains authoritative.
              </p>
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}
