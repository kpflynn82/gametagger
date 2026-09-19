import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  FlaskConical,
  GitCompareArrows,
} from "lucide-react";
import { api, words } from "./api";
import { Badge, Empty, ErrorMessage, PageHead } from "./App";
type Audit = {
  records: number;
  new_outcomes_all_tags: Record<string, number>;
  per_tag: Record<
    string,
    { new_outcomes: Record<string, number>; execution_errors: number }
  >;
  text_bearing_abstentions: {
    case_id: string;
    family_unknown_mass: number;
    global_unknown: number;
    top_nonnull: [string, number];
    semantic_cause: string;
  }[];
};
type LedgerCase = {
  id: string;
  status: string;
  comparison: string;
  old_primary_id: string | null;
  new_primary_id: string | null;
  source_relationship: string;
  evidence_available: boolean;
  failure_cause: string;
  cause_status: string;
  result_sha256: string;
  genre_distributions: Record<string, number> | null;
  tags: {
    tag_id: string;
    state: string;
    probabilities: Record<string, number>;
  }[];
};
type SavedReport = {
  id: string;
  kind: string;
  recommendation: string;
  reason: string;
  cohort: string;
  sample_size: number;
  label_provenance: string;
  label_version: string;
  comparison_eligibility: string;
  useful_contract: string;
  methods: { method_id: string; version: string }[];
  input_hashes: Record<string, string>;
  scorecard: {
    metric: string;
    baseline: number | null;
    candidate: number | null;
    change: number | null;
    paired_n: number;
    status: string;
    unit: string;
    reason: string | null;
    baseline_numerator: number | null;
    baseline_denominator: number;
    candidate_numerator: number | null;
    candidate_denominator: number;
  }[];
};
type Report = {
  reports: SavedReport[];
  report_errors: string[];
  case_ledger: LedgerCase[];
  recommendation: string;
  reason: string;
  scorecard: {
    metric: string;
    baseline: number | null;
    candidate: number | null;
    change: number | null;
    paired_n: number;
    status: string;
  }[];
  historical: Audit;
  provenance: Record<string, string>;
  clean_pilot: { target_cases: number; cases: unknown[] };
};
const legacy = [
  [
    "Name / record",
    "Repository-observed",
    "A legacy source lookup begins from the input name. Deployed lookup settings are unverified.",
  ],
  [
    "Source lookup",
    "Repository-observed",
    "Descriptions, configured screenshots and optional sampled trailer frames. Media was bypassed in the saved 100-record replay.",
  ],
  [
    "Combined model",
    "Repository-observed",
    "A generative model observes and classifies in one request. Actual deployed version is unverified.",
  ],
  [
    "Parse & mapping",
    "Repository-observed",
    "Legacy JSON parsing and label mapping. Not used by the new pipeline.",
  ],
  [
    "Saved tags",
    "Historical baseline",
    "Genre and boolean labels are machine annotations, not human truth.",
  ],
];
const modern = [
  [
    "Project identity",
    "Implemented",
    "Explicit publisher association or reviewed source identity. Unrelated sources are excluded.",
  ],
  [
    "Evidence preparation",
    "Implemented",
    "Attributed text, validated screenshots and experimental local MP4 windows.",
  ],
  [
    "Factual Observer",
    "Offline / live gated",
    "Exact text quotes are retained. Real image recognition requires separate spending authorization. Jev does not see raw media.",
  ],
  [
    "Jev decisions",
    "Live gated",
    "Typed decisions, strict distributions and isolated retries. Offline uploads have no model answer.",
  ],
  [
    "Policy & review",
    "Implemented",
    "One eligible primary, four-state attributes, separate execution states and human review.",
  ],
  [
    "Versioned catalog",
    "Implemented",
    "Private local persistence, evidence viewer, review history and redacted exports.",
  ],
];
export function Pipeline({ shared = false }: { shared?: boolean }) {
  const [detail, setDetail] = useState(
    "Select a stage to inspect what is actually implemented.",
  );
  const [method, setMethod] = useState("jev");
  const newer = shared
    ? [
        modern[2],
        [
          "Same saved observations",
          "Required for comparison",
          "Every method must bind identical observations, criteria, evidence and conditions.",
        ],
        [
          method === "jev" ? "Jev decisions" : "Conventional classifier",
          method === "jev" ? "Live gated" : "Comparator interface",
          method === "jev"
            ? "Existing Jev adapter is implemented. This screen makes no calls."
            : "Saved categorical/non-Jev result interface is implemented. No paid conventional-model run exists.",
        ],
        modern[4],
      ]
    : modern;
  return (
    <div className="pipeline-section">
      {shared && (
        <div className="segmented" aria-label="Classifier comparator">
          <button
            aria-pressed={method === "jev"}
            onClick={() => setMethod("jev")}
          >
            Jev
          </button>
          <button
            aria-pressed={method === "conventional"}
            onClick={() => setMethod("conventional")}
          >
            Conventional classifier
          </button>
        </div>
      )}
      <div className="pipeline-columns">
        {(shared
          ? [["Shared-observation comparison", newer]]
          : [
              ["Legacy combined flow", legacy],
              ["GameTagger evidence flow", newer],
            ]
        ).map(([name, stages]) => (
          <section key={String(name)} className="pipeline">
            <h3>{String(name)}</h3>
            {(stages as string[][]).map(([n, status, d], i) => (
              <div key={n}>
                <button onClick={() => setDetail(d)} title={d}>
                  <span className="node-number">{i + 1}</span>
                  <span>
                    <strong>{n}</strong>
                    <small>{status}</small>
                  </span>
                </button>
                {i < (stages as string[][]).length - 1 && (
                  <ArrowDown className="flow-arrow" size={17} />
                )}
              </div>
            ))}
          </section>
        ))}
      </div>
      <div role="status" className="node-detail">
        {detail}
      </div>
      <p className="field-note">
        Repository-observed legacy stages are not proof of deployed settings.
        The saved 100-record run used text only.
      </p>
    </div>
  );
}
export function Experiments() {
  const [data, setData] = useState<Report>();
  const [error, setError] = useState("");
  const [shared, setShared] = useState(false);
  const [selected, setSelected] =
    useState<Audit["text_bearing_abstentions"][number]>();
  const [tab, setTab] = useState("scorecard");
  const [slice, setSlice] = useState("all");
  const [ledgerCase, setLedgerCase] = useState<LedgerCase>();
  const [caseFilter, setCaseFilter] = useState("");
  const casePanel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (ledgerCase || selected) {
      casePanel.current?.focus();
      casePanel.current?.scrollIntoView({ block: "start" });
    }
  }, [ledgerCase, selected]);
  const [reportId, setReportId] = useState("");
  const activeReport = data?.reports?.find((r) => r.id === reportId);
  const scorecard = activeReport?.scorecard ?? data?.scorecard;
  const paired = Math.max(0, ...(scorecard?.map((r) => r.paired_n) ?? []));
  useEffect(() => {
    api<Report>("/experiments")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <PageHead
        eyebrow="JEV IMPACT / EXPERIMENTS"
        title="Make the case. Measure the difference."
      >
        <span>Does Jev improve useful results on the same evidence?</span>
      </PageHead>
      <ErrorMessage error={error} />
      {activeReport?.kind === "illustrative" && (
        <div className="notice" role="status">
          <strong>Illustrative / UI test data</strong> · Excluded from real
          measurements and aggregate effects.
        </div>
      )}
      <div className="recommendation">
        <FlaskConical size={24} />
        <div>
          <strong>
            {activeReport?.recommendation ??
              data?.recommendation ??
              "Loading evidence…"}
          </strong>
          <p>
            {activeReport?.reason ??
              data?.reason ??
              "Reading the experiment inventory."}
          </p>
        </div>
        <Badge>{paired} matched cases</Badge>
      </div>
      <label className="report-selector">
        Saved comparison
        <select
          value={reportId}
          onChange={(e) => {
            setReportId(e.target.value);
            setSlice("all");
          }}
        >
          <option value="">Clean pilot · no matched results</option>
          {data?.reports?.map((r) => (
            <option key={r.id} value={r.id}>
              {r.cohort} · {r.kind} · {r.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      {data?.report_errors?.map((e, i) => (
        <ErrorMessage key={i} error={e} />
      ))}
      <div className="comparison-controls">
        <label>
          Baseline
          <select>
            <option>
              {activeReport?.methods[0].method_id ??
                "Conventional classifier · results pending"}
            </option>
          </select>
        </label>
        <GitCompareArrows />
        <label>
          Candidate
          <select>
            <option>
              {activeReport?.methods[1].method_id ??
                "Jev hierarchy · matched results pending"}
            </option>
          </select>
        </label>
        <label>
          Cohort
          <select
            disabled={!!activeReport}
            value={slice}
            onChange={(e) => setSlice(e.target.value)}
          >
            {["all", "pc", "console", "mobile"].map((p) => (
              <option value={p} key={p}>
                {p === "all"
                  ? (activeReport?.cohort ?? "Clean pilot — all platforms")
                  : words(p)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="field-note">
        {data?.clean_pilot.cases.length ?? 0} checked cases available · 30
        target / 10 mobile-first minimum. No effect is computed for empty or
        incompatible cohorts.
      </p>
      <div className="segmented">
        {["scorecard", "pipelines", "performance", "quality"].map((t) => (
          <button key={t} aria-pressed={tab === t} onClick={() => setTab(t)}>
            {words(t)}
          </button>
        ))}
      </div>
      {tab === "scorecard" && (
        <section className="panel">
          <div className="section-head">
            <h2>Effectiveness scorecard</h2>
            <Badge>{activeReport?.kind ?? "Not measured"}</Badge>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Measure</th>
                  <th>Baseline</th>
                  <th>Jev</th>
                  <th>Change</th>
                  <th>Paired n</th>
                </tr>
              </thead>
              <tbody>
                {scorecard?.map((m) => (
                  <tr key={m.metric}>
                    <td>
                      {m.metric}
                      {"unit" in m && <small>{String(m.unit)}</small>}
                    </td>
                    <td>
                      {m.baseline === null
                        ? "Not measured"
                        : m.baseline.toFixed(2)}
                    </td>
                    <td>
                      {m.candidate === null
                        ? "Not measured"
                        : m.candidate.toFixed(2)}
                    </td>
                    <td>{m.change === null ? "—" : m.change.toFixed(2)}</td>
                    <td>
                      {m.paired_n}
                      <small>{m.status}</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {activeReport && (
            <details>
              <summary>
                Comparison eligibility, denominators and provenance
              </summary>
              <p>{activeReport.comparison_eligibility}</p>
              <p>
                Reference: {activeReport.label_provenance} ·{" "}
                {activeReport.label_version}. Useful-output contract:{" "}
                {activeReport.useful_contract}.
              </p>
              <p>
                Both methods use the frozen cohort. No automatic promotion;
                sparse results are descriptive only.
              </p>
              <pre>{JSON.stringify(activeReport, null, 2)}</pre>
            </details>
          )}
          <p className="field-note">
            Actual primary correctness includes abstentions and execution
            failures in the labelled eligible denominator. No accepted results
            means undefined precision.
          </p>
        </section>
      )}
      {tab === "pipelines" && (
        <section className="panel">
          <div className="section-head">
            <h2>Where the work happens</h2>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={shared}
                onChange={(e) => setShared(e.target.checked)}
              />
              Hold observations constant
            </label>
          </div>
          <Pipeline shared={shared} />
        </section>
      )}
      {tab === "performance" && (
        <section className="panel">
          <h2>End-to-end performance</h2>
          <p>
            Final-call timing is not total latency. No matched timing or
            complete cost ledger exists.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Duration</th>
                  <th>Cost</th>
                  <th>Conditions</th>
                </tr>
              </thead>
              <tbody>
                {[
                  "Queue",
                  "Acquisition",
                  "Media preparation",
                  "Observer",
                  "Classifier",
                  "Retries",
                  "Policy / persistence",
                  "Critical-path wall clock",
                ].map((s) => (
                  <tr key={s}>
                    <td>{s}</td>
                    <td>Not measured</td>
                    <td>Unknown</td>
                    <td>Cold/cache, concurrency and repetitions pending</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {tab === "quality" && (
        <div className="taxonomy-grid">
          {[
            [
              "Quality versus coverage",
              "Matched precision or coverage curves require reviewed paired cases.",
            ],
            [
              "Where Jev helps",
              "Per-tag deltas and genre confusion remain unmeasured. Sparse slices will show counts, not rankings.",
            ],
            [
              "Calibration",
              "Four-state Brier and reliability require compatible probabilities and evidence-supported human labels. Legacy confidence badges are not probabilities.",
            ],
          ].map(([t, p]) => (
            <section className="panel" key={t}>
              <Empty title={t}>
                <p>{p}</p>
                <Badge>0 paired cases · {slice}</Badge>
              </Empty>
            </section>
          ))}
        </div>
      )}
      <section className="panel historical">
        <div className="section-head">
          <div>
            <span className="eyebrow">PRESERVED ARTIFACT</span>
            <h2>100-record intake replay</h2>
          </div>
          <Badge tone="amber">Historical · text only</Badge>
        </div>
        <p>
          This is an intake stress test with unverified source associations, not
          100 verified games. Legacy agreement is not accuracy.
        </p>
        <div className="historical-counts">
          {[
            ["Completed", "97 / 100"],
            ["Terminal errors", "3 / 100"],
            ["Retry recovery", "9 / 12"],
            ["Human truth", "0 / 100"],
          ].map(([n, v]) => (
            <div key={n}>
              <span>{n}</span>
              <strong>{v}</strong>
            </div>
          ))}
        </div>
        <details>
          <summary>Provenance and comparison eligibility</summary>
          <dl>
            {data &&
              Object.entries(data.provenance).map(([k, v]) => (
                <div key={k}>
                  <dt>{words(k)}</dt>
                  <dd className="mono">{v}</dd>
                </div>
              ))}
          </dl>
          <p>
            Unpaired baseline. Exact source bodies and private provider
            responses are not sent to the browser.
          </p>
        </details>
        <details>
          <summary>All new tag outcomes · counts, not accuracy</summary>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tag</th>
                  <th>Present</th>
                  <th>Absent</th>
                  <th>Insufficient</th>
                  <th>Conflicting</th>
                  <th>Errors</th>
                </tr>
              </thead>
              <tbody>
                {data &&
                  Object.entries(data.historical.per_tag).map(([id, v]) => (
                    <tr key={id}>
                      <td>{words(id)}</td>
                      {[
                        "present",
                        "absent",
                        "insufficient_evidence",
                        "conflicting_evidence",
                      ].map((s) => (
                        <td key={s}>{v.new_outcomes[s]}</td>
                      ))}
                      <td>{v.execution_errors}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </details>
        <details>
          <summary>
            Eight text-bearing abstentions · inspect saved arithmetic
          </summary>
          <div className="case-buttons">
            {data?.historical.text_bearing_abstentions.map((c) => (
              <button key={c.case_id} onClick={() => setSelected(c)}>
                Record {c.case_id} <ArrowRight size={15} />
              </button>
            ))}
          </div>
        </details>
      </section>
      <section className="panel">
        <div className="section-head">
          <h2>Per-record comparison ledger</h2>
          <Badge>All 100 intake records retained</Badge>
        </div>
        <label>
          Filter saved outcome
          <select onChange={(e) => setCaseFilter(e.target.value)}>
            <option value="">All outcomes</option>
            <option value="error">Provider errors</option>
            <option value="Changed genre">Changed genre</option>
            <option value="Insufficient evidence">Insufficient evidence</option>
          </select>
        </label>
        <div className="table-wrap ledger-table">
          <table>
            <thead>
              <tr>
                <th>Record</th>
                <th>Historical primary</th>
                <th>New primary</th>
                <th>Outcome</th>
                <th>Inspect</th>
              </tr>
            </thead>
            <tbody>
              {data?.case_ledger
                .filter(
                  (c) =>
                    !caseFilter ||
                    c.status === caseFilter ||
                    c.comparison === caseFilter,
                )
                .map((c) => (
                  <tr key={c.id}>
                    <td>{c.id}</td>
                    <td>
                      {c.old_primary_id
                        ? words(c.old_primary_id)
                        : "Unmapped / unavailable"}
                    </td>
                    <td>
                      {c.new_primary_id
                        ? words(c.new_primary_id)
                        : "None emitted"}
                    </td>
                    <td>{c.comparison}</td>
                    <td>
                      <button onClick={() => setLedgerCase(c)}>
                        Inspect {c.id}
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>
      {ledgerCase && (
        <section
          ref={casePanel}
          tabIndex={-1}
          className="panel case-drawer"
          aria-label="Saved case detail"
        >
          <div className="section-head">
            <h2>Saved record {ledgerCase.id}</h2>
            <button onClick={() => setLedgerCase(undefined)}>
              Close saved case
            </button>
          </div>
          <Badge tone="amber">Historical replay · no human truth</Badge>
          <p>
            Source relationship: {ledgerCase.source_relationship}. Evidence
            available:{" "}
            {ledgerCase.evidence_available
              ? "text only"
              : "no usable description"}
            .
          </p>
          <p>
            Failure cause: {words(ledgerCase.failure_cause)} (
            {ledgerCase.cause_status}).
          </p>
          <p className="mono">Result hash: {ledgerCase.result_sha256}</p>
          <details>
            <summary>Full available genre distribution</summary>
            <pre>{JSON.stringify(ledgerCase.genre_distributions, null, 2)}</pre>
          </details>
          <details>
            <summary>Attribute states and preserved distributions</summary>
            <pre>{JSON.stringify(ledgerCase.tags, null, 2)}</pre>
          </details>
          <p>
            Private sources and original labels are not human truth. Media
            playback is unavailable for this text-only run.
          </p>
        </section>
      )}
      {selected && (
        <section
          ref={casePanel}
          tabIndex={-1}
          className="panel case-drawer"
          aria-label="Case comparison"
        >
          <div className="section-head">
            <h2>Record {selected.case_id}</h2>
            <button onClick={() => setSelected(undefined)}>Close case</button>
          </div>
          <Badge tone="amber">Identity and cause unreviewed</Badge>
          <dl>
            <dt>Original family unknown mass</dt>
            <dd>{selected.family_unknown_mass.toFixed(4)}</dd>
            <dt>Derived global unknown</dt>
            <dd>{selected.global_unknown.toFixed(4)}</dd>
            <dt>Highest non-null candidate</dt>
            <dd>
              {words(selected.top_nonnull[0])} ·{" "}
              {selected.top_nonnull[1].toFixed(4)}
            </dd>
          </dl>
          <p>{selected.semantic_cause}</p>
          <p>
            No primary was emitted. These are model scores, not calibrated
            correctness percentages. Private source text/media is withheld.
          </p>
        </section>
      )}
    </>
  );
}
type Status = {
  checked_at: string;
  timezone: string;
  runtime: string;
  head_sha: string;
  branch: string;
  live_budget: string;
  milestones: {
    id: string;
    name: string;
    goal: string;
    status: string;
    implemented: boolean;
    tested: boolean;
    quality_measured: boolean;
    dependency: string | null;
    pr: string | null;
    sha: string | null;
    test_artifact: string | null;
    blocker: string | null;
    next_action: string;
  }[];
};
export function Roadmap() {
  const [s, setStatus] = useState<Status>();
  const [error, setError] = useState("");
  useEffect(() => {
    api<Status>("/roadmap")
      .then(setStatus)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <PageHead eyebrow="ROADMAP / BOUNDED BUILD" title="The next useful step.">
        Implementation, tests and measured quality are separate milestones.
      </PageHead>
      <ErrorMessage error={error} />
      <div className="notice">
        Runtime unknown. This saved status is not evidence that a coding agent
        is running.
        <br />
        {s && (
          <>
            Checked{" "}
            {new Date(s.checked_at).toLocaleString("en-US", {
              timeZone: "America/Los_Angeles",
            })}{" "}
            Pacific ·{" "}
            {Date.now() - Date.parse(s.checked_at) > 3600000
              ? "Snapshot stale"
              : "Saved snapshot"}
          </>
        )}
      </div>
      <div className="roadmap">
        {s?.milestones.map((m) => (
          <section key={m.id} className="roadmap-row">
            <div className="milestone-number">{m.id}</div>
            <div className="panel">
              <div className="section-head">
                <h2>{m.name}</h2>
                <Badge tone={m.status === "blocked" ? "amber" : "neutral"}>
                  {m.status}
                </Badge>
              </div>
              <p>{m.goal}</p>
              <div className="dimension-chips">
                <Badge>Implemented: {m.implemented ? "yes" : "pending"}</Badge>
                <Badge>Tested: {m.tested ? "yes" : "pending"}</Badge>
                <Badge>
                  Quality: {m.quality_measured ? "measured" : "not measured"}
                </Badge>
              </div>
              <dl>
                <dt>Dependency</dt>
                <dd>{m.dependency ?? "None"}</dd>
                <dt>Latest check</dt>
                <dd>{m.test_artifact ?? "Pending"}</dd>
                <dt>Next action</dt>
                <dd>{m.next_action}</dd>
                {m.blocker && (
                  <>
                    <dt>Blocker</dt>
                    <dd>{m.blocker}</dd>
                  </>
                )}
              </dl>
              {m.pr && (
                <a href={m.pr} target="_blank" rel="noreferrer">
                  Review PR <ArrowRight size={14} />
                </a>
              )}
              {m.sha && <small className="mono">{m.sha}</small>}
            </div>
          </section>
        ))}
      </div>
      <p className="mono">
        Branch: {s?.branch} · Revision: {s?.head_sha}
      </p>
    </>
  );
}
