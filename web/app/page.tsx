"use client";

import { FormEvent, useMemo, useState } from "react";

type Action =
  | "doctor"
  | "demo"
  | "status"
  | "buy"
  | "statement"
  | "mission"
  | "proof";
type MissionData = {
  kind: "mission";
  mission: string;
  planner: string;
  model: string;
  decision: { offerId: string; rationale: string; guardrail: string };
  offers: Array<{
    id: string;
    title: string;
    description: string;
    amount: string;
    instrument: string;
    eligible: boolean;
    selected: boolean;
  }>;
  receipt: { contractId: string; amount: string; businessReference: string } | null;
  remaining: string;
  spent: string;
  totalCap: string;
};
type ProofData = {
  kind: "proof";
  mandateId: string;
  legitimateReceipt: string;
  spent: string;
  totalCap: string;
  receiptCount: number;
  revoked: boolean;
  steps: Array<{
    id: string;
    title: string;
    status: string;
    detail: string;
    boundary: string;
  }>;
};
type StructuredData = MissionData | ProofData;
type ApiResponse = {
  ok: boolean;
  action?: Action;
  output?: string;
  warning?: string;
  error?: string;
  durationMs?: number;
  data?: StructuredData;
};
type Activity = ApiResponse & { id: number; at: string };

const actionLabels: Record<Action, string> = {
  doctor: "Environment doctor",
  demo: "Create demo wallet",
  status: "Refresh mandate",
  buy: "Purchase",
  statement: "Load statement",
  mission: "Agent mission",
  proof: "Automated proof",
};

function structuredSummary(data: StructuredData): string {
  if (data.kind === "mission") {
    return [
      "AGENT MISSION COMPLETE",
      `mission           ${data.mission}`,
      `planner           ${data.planner}${data.model !== "none" ? ` · ${data.model}` : ""}`,
      `selected          ${data.decision.offerId}`,
      `reason            ${data.decision.rationale}`,
      `guardrail         ${data.decision.guardrail}`,
      `receipt           ${data.receipt?.contractId || "—"}`,
      `remaining         ${data.remaining}`,
    ].join("\n");
  }
  return [
    "AUTOMATED PROOF COMPLETE",
    ...data.steps.map((step) =>
      `${step.status === "rejected" ? "BLOCKED" : "PASS"}  ${step.title}`,
    ),
    `receipts          ${data.receiptCount}`,
    `revoked           ${data.revoked ? "yes" : "no"}`,
  ].join("\n");
}

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
    "Check the environment, then create a wallet to begin the D1 demo.",
  );
  const [statusOutput, setStatusOutput] = useState("");
  const [statementOutput, setStatementOutput] = useState("");
  const [demoAmount, setDemoAmount] = useState("0.1");
  const [demoCap, setDemoCap] = useState("1.0");
  const [buyAmount, setBuyAmount] = useState("0.05");
  const [reference, setReference] = useState("ui-order-001");
  const [goal, setGoal] = useState(
    "Buy the best approved data service within my remaining allowance.",
  );
  const [missionData, setMissionData] = useState<MissionData | null>(null);
  const [proofData, setProofData] = useState<ProofData | null>(null);

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

    const output =
      result.output ||
      result.error ||
      (result.data ? structuredSummary(result.data) : "No output returned");
    setLatestOutput(output);
    if (result.ok && action === "status") setStatusOutput(result.output || "");
    if (result.ok && action === "statement") {
      setStatementOutput(result.output || "");
    }
    if (result.ok && result.data?.kind === "mission") {
      setMissionData(result.data);
    }
    if (result.ok && result.data?.kind === "proof") {
      setProofData(result.data);
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

  const handleMission = async (event: FormEvent) => {
    event.preventDefault();
    const result = await run("mission", { goal });
    if (result.ok) {
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
  const hasWallet = metrics.status !== "—";
  const latestActivity = activity[0];

  return (
    <div className="appShell">
      <a className="skipLink" href="#main-content">Skip to demo</a>

      <header className="siteHeader">
        <div className="headerInner">
          <div className="brand">
            <span className="brandMark" aria-hidden="true">D1</span>
            <div>
              <strong>Spend-limited agent wallet</strong>
              <span>Canton hackathon demo</span>
            </div>
          </div>
          <div className="networkStatus">
            <span className="statusDot" aria-hidden="true" />
            LocalNet test environment
          </div>
        </div>
      </header>

      <main id="main-content" className="shell" aria-busy={busy}>
        <section className="intro" aria-labelledby="page-title">
          <div className="introCopy">
            <p className="sectionLabel">Daml challenge D1</p>
            <h1 id="page-title">A wallet with limits the agent cannot bypass</h1>
            <p>
              Set a spending mandate once. Canton enforces the budget, approved
              recipients, expiry and revocation on the ledger.
            </p>
          </div>
          <div className="environmentCheck">
            <button
              className="button buttonSecondary"
              disabled={busy}
              onClick={() => run("doctor")}
              type="button"
            >
              {running === "doctor" ? "Checking environment…" : "Check environment"}
            </button>
            <span>Requires LocalNet and the Daml CLI</span>
          </div>
        </section>

        <section className="contractSummary" aria-labelledby="contract-heading">
          <div className="summaryIntro">
            <p className="sectionLabel">Contract boundary</p>
            <h2 id="contract-heading">Enforced in Daml</h2>
          </div>
          <dl className="guardrailList">
            <div>
              <dt>Total spend cap</dt>
              <dd>Every charge checks the remaining allowance.</dd>
            </div>
            <div>
              <dt>Approved recipients</dt>
              <dd>The merchant must be on the mandate allow-list.</dd>
            </div>
            <div>
              <dt>Expiry</dt>
              <dd>An expired mandate cannot authorize a payment.</dd>
            </div>
            <div>
              <dt>Owner revocation</dt>
              <dd>The owner can revoke; the agent cannot interfere.</dd>
            </div>
          </dl>
        </section>

        <div className="workspace">
          <section className="workflowPanel" aria-labelledby="demo-heading">
            <div className="panelHeading">
              <div>
                <p className="sectionLabel">Guided demo</p>
                <h2 id="demo-heading">Run the D1 flow</h2>
              </div>
              <p>Setup → purchase → adversarial proof</p>
            </div>

            <form className="workflowStep" onSubmit={handleDemo}>
              <div className="stepNumber" aria-hidden="true">1</div>
              <div className="stepContent">
                <div className="stepHeading">
                  <div>
                    <h3>Create a funded mandate</h3>
                    <p>
                      Provision fresh owner, agent and merchant identities, then
                      make the first allowed purchase.
                    </p>
                  </div>
                  <span className="stepType">Setup</span>
                </div>
                <div className="inputRow">
                  <label htmlFor="demo-amount">
                    First purchase
                    <div className="inputWithUnit">
                      <input
                        id="demo-amount"
                        inputMode="decimal"
                        min="0.001"
                        required
                        step="0.001"
                        type="number"
                        value={demoAmount}
                        onChange={(event) => setDemoAmount(event.target.value)}
                      />
                      <span>Amulet</span>
                    </div>
                  </label>
                  <label htmlFor="demo-cap">
                    Total spend cap
                    <div className="inputWithUnit">
                      <input
                        id="demo-cap"
                        inputMode="decimal"
                        min="0.002"
                        required
                        step="0.001"
                        type="number"
                        value={demoCap}
                        onChange={(event) => setDemoCap(event.target.value)}
                      />
                      <span>Amulet</span>
                    </div>
                  </label>
                </div>
                <p className="fieldHelp">The cap must be higher than the first purchase.</p>
                <button className="button buttonPrimary" disabled={busy} type="submit">
                  {running === "demo" ? "Creating wallet…" : "Create wallet and purchase"}
                </button>
              </div>
            </form>

            <form className="workflowStep" onSubmit={handleMission}>
              <div className="stepNumber" aria-hidden="true">2</div>
              <div className="stepContent">
                <div className="stepHeading">
                  <div>
                    <h3>Let the agent choose an approved offer</h3>
                    <p>
                      The planner chooses an offer ID. Trusted code resolves the
                      payment fields and the mandate still decides whether it can commit.
                    </p>
                  </div>
                  <span className="stepType">Purchase</span>
                </div>
                <label className="missionField" htmlFor="mission-goal">
                  Task for the agent
                  <textarea
                    id="mission-goal"
                    value={goal}
                    maxLength={500}
                    required
                    rows={3}
                    onChange={(event) => setGoal(event.target.value)}
                  />
                </label>
                <p className="fieldHelp">
                  Uses the deterministic policy planner by default; model ranking is optional.
                </p>
                <button className="button buttonPrimary" disabled={busy} type="submit">
                  {running === "mission" ? "Evaluating approved offers…" : "Run agent purchase"}
                </button>

                {missionData ? (
                  <section className="missionResult" aria-live="polite" aria-label="Agent purchase result">
                    <div className="resultHeading">
                      <div>
                        <span>Selected offer</span>
                        <strong>{missionData.decision.offerId}</strong>
                      </div>
                      <span className="resultStatus">Committed</span>
                    </div>
                    <p>{missionData.decision.rationale}</p>
                    <div className="guardrailCallout">
                      <strong>Why it was allowed</strong>
                      <span>{missionData.decision.guardrail}</span>
                    </div>
                    <div className="offerGrid" aria-label="Offers considered">
                      {missionData.offers.map((offer) => (
                        <article
                          className={`offerCard ${offer.selected ? "selectedOffer" : ""} ${!offer.eligible ? "blockedOffer" : ""}`}
                          key={offer.id}
                        >
                          <div className="offerHeading">
                            <strong>{offer.title}</strong>
                            <span>{offer.amount} {offer.instrument}</span>
                          </div>
                          <p>{offer.description}</p>
                          <small>
                            {offer.selected ? "Purchased" : offer.eligible ? "Allowed" : "Blocked by mandate"}
                          </small>
                        </article>
                      ))}
                    </div>
                  </section>
                ) : null}
              </div>
            </form>

            <section className="workflowStep proofStepSection" aria-labelledby="proof-heading">
              <div className="stepNumber" aria-hidden="true">3</div>
              <div className="stepContent">
                <div className="stepHeading">
                  <div>
                    <h3 id="proof-heading">Prove the limits hold</h3>
                    <p>
                      Run an isolated judge demo: a valid charge, over-cap and
                      unapproved-recipient attempts, owner revocation, then a final audit.
                    </p>
                  </div>
                  <span className="stepType">Proof</span>
                </div>
                <button
                  className="button buttonSecondary"
                  disabled={busy}
                  onClick={() => run("proof")}
                  type="button"
                >
                  {running === "proof" ? "Testing contract boundaries…" : "Run boundary tests"}
                </button>
                <p className="fieldHelp">Proof mode uses a disposable wallet and revokes it at the end.</p>

                {proofData ? (
                  <div className="proofResults" aria-live="polite">
                    <ul>
                      {proofData.steps.map((step) => {
                        const blocked = step.status === "rejected";
                        return (
                          <li key={step.id}>
                            <span className={`resultMark ${blocked ? "blocked" : "passed"}`} aria-hidden="true">
                              {blocked ? "×" : "✓"}
                            </span>
                            <div>
                              <strong>{step.title}</strong>
                              <p>{step.detail}</p>
                              <small>{step.boundary}</small>
                            </div>
                            <span className="proofStatus">{blocked ? "Blocked as expected" : "Passed"}</span>
                          </li>
                        );
                      })}
                    </ul>
                    <div className="proofSummary">
                      <span>{proofData.receiptCount} legitimate receipt</span>
                      <span>{proofData.revoked ? "Mandate revoked" : "Mandate active"}</span>
                    </div>
                  </div>
                ) : null}
              </div>
            </section>

            <details className="manualTools">
              <summary>Manual purchase and operator controls</summary>
              <div className="manualContent">
                <p>
                  Submit a fixed charge without the planner, or use it while
                  presenting individual wallet operations.
                </p>
                <form onSubmit={handleBuy}>
                  <div className="inputRow purchaseInputs">
                    <label htmlFor="purchase-amount">
                      Purchase amount
                      <div className="inputWithUnit">
                        <input
                          id="purchase-amount"
                          inputMode="decimal"
                          min="0.001"
                          required
                          step="0.001"
                          type="number"
                          value={buyAmount}
                          onChange={(event) => setBuyAmount(event.target.value)}
                        />
                        <span>Amulet</span>
                      </div>
                    </label>
                    <label htmlFor="business-reference">
                      Business reference
                      <input
                        id="business-reference"
                        value={reference}
                        maxLength={128}
                        pattern="[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
                        required
                        onChange={(event) => setReference(event.target.value)}
                      />
                    </label>
                  </div>
                  <button className="button buttonPrimary" disabled={busy} type="submit">
                    {running === "buy" ? "Submitting purchase…" : "Submit manual purchase"}
                  </button>
                </form>
              </div>
            </details>
          </section>

          <aside className="evidenceColumn" aria-label="Wallet state and ledger evidence">
            <section className="sideCard walletCard" aria-labelledby="wallet-state-heading">
              <div className="sideCardHeading">
                <div>
                  <p className="sectionLabel">Current wallet</p>
                  <h2 id="wallet-state-heading">Mandate state</h2>
                </div>
                <button className="textButton" disabled={busy} onClick={handleRefresh} type="button">
                  {running === "status" || running === "statement" ? "Refreshing…" : "Refresh"}
                </button>
              </div>
              <dl className="walletMetrics">
                <div>
                  <dt>Status</dt>
                  <dd className={metrics.status === "active" ? "activeText" : ""}>
                    {hasWallet ? metrics.status : "Not created"}
                  </dd>
                </div>
                <div>
                  <dt>Spent / cap</dt>
                  <dd>{hasWallet ? metrics.allowance : "—"}</dd>
                </div>
                <div>
                  <dt>Remaining</dt>
                  <dd>{hasWallet ? metrics.remaining : "—"}</dd>
                </div>
                <div>
                  <dt>Receipts</dt>
                  <dd>{metrics.receipts === "—" ? "0" : metrics.receipts}</dd>
                </div>
              </dl>
              <div className="mandateId">
                <span>Mandate ID</span>
                <code title={field(statusOutput, "mandate")}>
                  {hasWallet ? metrics.mandate : "Available after setup"}
                </code>
              </div>
            </section>

            <section
              className={`sideCard outputCard ${latestActivity && !latestActivity.ok ? "outputError" : ""}`}
              aria-labelledby="ledger-output-heading"
            >
              <div className="sideCardHeading outputHeading">
                <div>
                  <p className="sectionLabel">Ledger evidence</p>
                  <h2 id="ledger-output-heading">Latest result</h2>
                </div>
                <button
                  className="textButton"
                  disabled={busy}
                  onClick={() => run("statement")}
                  type="button"
                >
                  {running === "statement" ? "Loading…" : "View statement"}
                </button>
              </div>
              <div className="runState" aria-live="polite">
                <span className={busy ? "runIndicator busy" : "runIndicator"} aria-hidden="true" />
                {running
                  ? `${actionLabels[running]} in progress`
                  : latestActivity
                    ? latestActivity.ok ? "Last action completed" : "Last action needs attention"
                    : "Ready"}
              </div>
              <pre aria-live="polite" aria-atomic="true">{latestOutput}</pre>
            </section>

            <section className="sideCard activityCard" aria-labelledby="activity-heading">
              <div className="sideCardHeading">
                <div>
                  <p className="sectionLabel">This session</p>
                  <h2 id="activity-heading">Recent actions</h2>
                </div>
              </div>
              <div className="activityList">
                {activity.length === 0 ? (
                  <p className="emptyState">Actions will appear here as you run the demo.</p>
                ) : activity.map((item) => (
                  <div className="activityItem" key={item.id}>
                    <span className={item.ok ? "resultMark passed" : "resultMark failed"} aria-hidden="true">
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

            <section className="securityNote" aria-labelledby="agent-boundary-heading">
              <h2 id="agent-boundary-heading">What the planner cannot control</h2>
              <p>
                It cannot choose the ledger user, owner, canonical merchant,
                token, template, choice or raw command. It can return only a public offer ID.
              </p>
            </section>
          </aside>
        </div>
      </main>
    </div>
  );
}
