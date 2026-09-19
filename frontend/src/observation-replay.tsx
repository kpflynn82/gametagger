import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Run } from "./api";

export function ObservationReplayPanel({
  run,
  reviewer,
}: {
  run: Run;
  reviewer: boolean;
}) {
  const [file, setFile] = useState<File>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const windows = run.observation_windows ?? [];
  const executions = run.observation_executions ?? [];
  const provenance = run.provenance ?? {};
  const eligible =
    run.mode === "offline" &&
    run.status === "partial" &&
    run.identity_status === "associated_project" &&
    windows.length > 0;
  return (
    <section className="panel observation-replay">
      <div className="eyebrow">SAVED OBSERVATIONS · NO NEW INFERENCE</div>
      <h2>Replay an observed window</h2>
      <p>
        Import a saved structured response for these exact frames. Evidence,
        timestamps, model, prompt and taxonomy provenance must match. This
        creates a new saved run; the original stays unchanged.
      </p>
      <p className="field-note">
        Imported claims are not human-verified. A matched hash cannot
        authenticate the provider. Genres and attributes remain not evaluated.
      </p>
      <p>
        {windows.length} bounded windows available. Gaps between sampled windows
        cannot establish action timing.
      </p>
      {executions.length > 0 && (
        <ul aria-label="Window execution status">
          {executions.map((e) => (
            <li key={String(e.window_sha256)}>
              <code>{String(e.window_sha256).slice(0, 10)}</code> ·{" "}
              {String(e.status).replaceAll("_", " ")}
              {Boolean(e.error_code) && (
                <span> · {String(e.error_code).replaceAll("_", " ")}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {eligible ? (
        <>
          <a
            className="button"
            download="observation-request.json"
            href={`/api/runs/${run.id}/observation-request`}
          >
            Download exact window manifest
          </a>
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              if (!file) return;
              setError("");
              setBusy(true);
              try {
                if (file.size > 512 * 1024)
                  throw new Error("Replay file limit: 512 KiB.");
                const replay: unknown = JSON.parse(await file.text());
                const result = await api<Run>(
                  `/runs/${run.id}/observation-replay`,
                  {
                    method: "POST",
                    body: JSON.stringify({
                      idempotency_key: crypto.randomUUID(),
                      replay,
                    }),
                  },
                );
                navigate(`/runs/${result.id}`);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Saved observation JSON
              <input
                type="file"
                accept="application/json,.json"
                disabled={!reviewer || busy}
                onChange={(e) => {
                  setFile(e.target.files?.[0]);
                  setError("");
                }}
              />
            </label>
            {error && <p role="alert">{error}</p>}
            <button className="button" disabled={!reviewer || !file || busy}>
              {busy ? "Checking saved provenance…" : "Validate and save replay"}
            </button>
            {!reviewer && (
              <p>Reviewer role is required to import saved claims.</p>
            )}
          </form>
        </>
      ) : (
        <p className="muted">
          {run.mode === "observation_replay"
            ? "This is a saved replay. Open its original preparation run to import another response."
            : "Prepare an associated local clip with at least two nearby sampled frames first."}
        </p>
      )}
      {typeof provenance.parent_run_id === "string" && (
        <a href={`/runs/${provenance.parent_run_id}`}>
          Open original preparation run
        </a>
      )}
    </section>
  );
}
