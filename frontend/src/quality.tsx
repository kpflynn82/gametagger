import { useState } from "react";
export type Measure = { value: number | null; numerator: number; denominator: number };
type Bucket = { lower: number; upper: number; count: number; mean_selected_probability: Measure; empirical_correctness: Measure };
type TagMetrics = {
  human_supported_labels: number; records: number; errors: number; not_evaluated: number;
  accepted_precision: Measure; accepted_only_recall: Measure; end_to_end_positive_recovery: Measure;
  four_state_brier_sum_over_classes: Measure; game_truth_positive_recovery: Measure;
  calibration: Bucket[];
};
export type Quality = {
  available: boolean; reason: string | null; target: string; paired_games: number; assigned_games: number;
  identity_excluded_games?: number; pending_reference_games?: number;
  tags: { id: string; label: string; category: string; baseline: TagMetrics; candidate: TagMetrics;
    precision_change_pp: number | null; recall_change_pp: number | null; warning: string }[];
  genre?: { baseline: { confusion_counts: {truth: string; prediction: string; count: number}[] };
    candidate: { confusion_counts: {truth: string; prediction: string; count: number}[] } };
};
const metric = (m: Measure, percent = true) => m.value === null ? `Not measured (n=${m.denominator})`
  : `${(m.value * (percent ? 100 : 1)).toFixed(2)}${percent ? "%" : ""} (${m.numerator.toFixed(2)} / ${m.denominator})`;

export function QualityView({ quality }: { quality?: Quality }) {
  const [tagId, setTagId] = useState("");
  const tag = quality?.tags.find(t => t.id === tagId) ?? quality?.tags[0];
  if (!quality?.available) return <section className="panel">
    <h2>Evidence-supported quality</h2>
    <p>{quality?.reason ?? "No compatible paired case measurements are available."}</p>
    <p>Per-tag precision, end-to-end recall and four-state calibration remain <strong>Not measured</strong>.
      Historical agreement and model confidence cannot fill these values.</p>
  </section>;
  return <>
    <section className="panel">
      <h2>Attribute precision and recovery</h2>
      <p>{quality.assigned_games} assigned games · {quality.paired_games} paired reviewed games ·
        {" "}{quality.identity_excluded_games ?? 0} excluded by identity · {quality.pending_reference_games ?? 0} references pending.</p>
      <p>Target: {quality.target}. Counts are game/tag judgments; uncertainty must cluster by game.
        Sparse slices are descriptive, not a ranking of proven improvements.</p>
      <div className="table-wrap"><table>
        <thead><tr><th>Attribute</th><th>Baseline precision</th><th>Candidate precision</th><th>Precision Δ pp</th>
          <th>Baseline end-to-end recall</th><th>Candidate end-to-end recall</th></tr></thead>
        <tbody>{quality.tags.map(t => <tr key={t.id}><td>{t.label}</td>
          <td>{metric(t.baseline.accepted_precision)}</td><td>{metric(t.candidate.accepted_precision)}</td>
          <td>{t.precision_change_pp === null ? "Not measured" : t.precision_change_pp.toFixed(2)}</td>
          <td>{metric(t.baseline.end_to_end_positive_recovery)}</td><td>{metric(t.candidate.end_to_end_positive_recovery)}</td>
        </tr>)}</tbody></table></div>
    </section>
    <section className="panel">
      <h2>Calibration and execution detail</h2>
      <label>Attribute detail<select value={tag?.id ?? ""} onChange={e => setTagId(e.target.value)}>
        {quality.tags.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
      </select></label>
      {tag && <>
        <p>{tag.warning}</p>
        <p>The probability target is the four-state judgment supported by this evidence,
          not game-wide feature existence. No calibration claim is made from a sparse bucket.</p>
        <div className="quality-pair">{(["baseline", "candidate"] as const).map(method => {
          const m = tag[method];
          return <article key={method}>
            <h3>{method === "baseline" ? "Baseline" : "Candidate"}</h3>
            <p>Errors: {m.errors} / {m.records} · Not evaluated: {m.not_evaluated} / {m.records}</p>
            <p>Accepted-only recall: {metric(m.accepted_only_recall)}</p>
            <p>End-to-end supported recall: {metric(m.end_to_end_positive_recovery)}</p>
            <p>Game-truth positive recovery: {metric(m.game_truth_positive_recovery)}</p>
            <p>Four-state Brier (sum over classes): {metric(m.four_state_brier_sum_over_classes, false)}</p>
            <Reliability buckets={m.calibration} method={method} />
          </article>;
        })}</div>
      </>}
    </section>
    <section className="panel">
      <h2>Genre confusion counts</h2>
      <p>No per-genre accuracy is inferred from sparse examples. “No emitted primary” includes abstention and execution failures.</p>
      <div className="table-wrap"><table><thead><tr><th>Method</th><th>Reference</th><th>Emitted primary</th><th>Count</th></tr></thead>
        <tbody>{(["baseline", "candidate"] as const).flatMap(method =>
          quality.genre?.[method].confusion_counts.map((c,i) => <tr key={`${method}-${i}`}>
            <td>{method}</td><td>{c.truth}</td><td>{c.prediction}</td><td>{c.count}</td></tr>) ?? [])}</tbody>
      </table></div>
    </section>
    <section className="panel"><h2>Quality versus coverage</h2>
      <p>Precision is shown alongside end-to-end recovery. Matched-coverage curves and promotion thresholds
        require a preregistered sweep; a single operating point is not a curve.</p></section>
  </>;
}

function Reliability({ buckets, method }: { buckets: Bucket[]; method: string }) {
  const occupied = buckets.filter(b => b.count > 0);
  // A small single bucket is useful as a count, not a persuasive calibration plot.
  const supported = occupied.filter(b => b.count >= 5);
  return <>
    {supported.length >= 2 ? <svg viewBox="0 0 300 260" role="img" aria-label={`${method} reliability; table below contains exact values`}>
      <title>{method}: predicted selected-state probability versus empirical correctness</title>
      <line x1="35" y1="215" x2="265" y2="215" stroke="currentColor" />
      <line x1="35" y1="215" x2="35" y2="15" stroke="currentColor" />
      <line x1="35" y1="215" x2="265" y2="15" stroke="#858b97" strokeDasharray="4 4" />
      <text x="75" y="250">Selected-state probability</text>
      <text x="40" y="12">Empirical correctness</text>
      {supported.map(b => <g key={b.lower} tabIndex={0} role="img"
        aria-label={`Bucket ${b.lower} to ${b.upper}, n=${b.count}, probability=${b.mean_selected_probability.value}, correctness=${b.empirical_correctness.value}`}>
        <title>{b.lower}–{b.upper}, n={b.count}</title>
        <circle cx={35 + 230 * (b.mean_selected_probability.value ?? 0)} cy={215 - 200 * (b.empirical_correctness.value ?? 0)} r="5" fill="#514ac6" />
      </g>)}
    </svg> : <p>Plot deferred: at least two buckets with five cases each are required. Available counts remain below.</p>}
    <div className="table-wrap"><table><caption>{method} reliability buckets · evidence-supported target</caption>
      <thead><tr><th>Bucket</th><th>Count</th><th>Mean model score</th><th>Correctness</th></tr></thead>
      <tbody>{occupied.length ? occupied.map(b => <tr key={b.lower}><td>{b.lower.toFixed(1)}–{b.upper.toFixed(1)}</td>
        <td>{b.count}</td><td>{metric(b.mean_selected_probability)}</td><td>{metric(b.empirical_correctness)}</td></tr>)
        : <tr><td colSpan={4}>Not measured · no valid labelled distributions</td></tr>}</tbody>
    </table></div>
  </>;
}
