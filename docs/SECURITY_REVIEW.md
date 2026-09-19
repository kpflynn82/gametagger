# Local workspace self-review

This is the implementation author's code/security review, **not independent approval**. Review focuses on the intended loopback-only, single-user operating boundary. Exact tested revision and CI are recorded in SESSION_REPORT and the PR. No merge is authorized by this document.

Inspected: workspace app/contracts/store/service, media child process, comparison contracts, existing identity/evidence and Jev partial-result paths, Observer boundary, metrics, browser routes/forms/exports and CI. Original taxonomy and immutable experiment inventory were compared to baseline. Sanitized ledger was reproduced from the hash-verified original files; source text, names, URLs and raw error bodies are excluded.

Controls verified by tests:

- Disabled unless explicitly configured; peer/Host/Origin enforcement, same-origin write header, no trust in forwarded client IP, reviewer role enforced by server, owner-scoped project/run/media reads.
- No live request path can bypass the spend gate; keys are not loaded by startup. Provider SDK integration remains separate. No arbitrary URL fetch or inference in browser code.
- Strict input limits, content decoding, generated paths, re-encoded still previews, media byte/pixel/duration/CPU/output/time limits; child-process resource limits avoid unsafe threaded pre-exec hooks. Frame images fit a 640×640 box, including tall inputs.
- Versioned CAS reviews, bound idempotency, durable restart interruption, cancellation protected from stale worker saves, immutable per-run sampled frames, original media hash verification. Derived media also reserves quota before decoding.
- Literal text attribution remains separate from conclusions; no relaxation of provider probability totals. Offline execution has null semantic decisions, not manufactured insufficient-evidence distributions.
- Paired effects require compatible evidence/observation/cohort/taxonomy/condition/reference versions. Nonfinite/negative timings or costs are rejected. Illustrative reports are labelled and excluded; empty denominators are undefined.
- React escapes source content; CSP and no-sniff headers; redacted JSON/CSV exports and formula neutralization. No raw private evidence in public test/report artifacts.

Defects found and fixed during this pass: stale review revision handling, stale cancellation writes, shared frame directories overwriting older-run pointers, metadata provenance missing the input hash, video aspect-ratio resource bounds, body limits without Content-Length, ambiguous mobile API status, and intake count checks before awaited uploads/concurrent project creation. Final application source: `d8bf3fedf58bccb1ca1e136a42c358c55cc13c47`. Test harness issues (invalid synthetic PNG, inaccurate selectors, reduced-motion captures) were corrected without weakening product assertions. A TypeScript narrowing error in metric-unit rendering was fixed before delivery.

Remaining boundaries: not production auth, not a multi-process queue, no universal URL adapters, no independent human identity certification, no real ordered-video Observer yet, no live spend ledger/executor. macOS has CPU/allocation/file/time constraints but no Linux-style address-space ceiling. Do not tunnel or deploy this development server publicly. A separate reviewer must assess the exact PR head before any merge; passing self-tests is not independent review.
