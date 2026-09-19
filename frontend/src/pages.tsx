import { useEffect, useRef, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  FileImage,
  Film,
  Plus,
  Upload,
} from "lucide-react";
import {
  api,
  type Capabilities,
  type Catalog,
  type Project,
  type ProjectInput,
  type Review,
  type Run,
  type Taxonomy,
  words,
} from "./api";
import { Badge, Empty, ErrorMessage, PageHead } from "./App";
function useLoad<T>(path: string) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setData(undefined);
    setError("");
    api<T>(path)
      .then((v) => {
        if (active) setData(v);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [path]);
  return { data, error };
}
export function Overview() {
  const [dataset, setDataset] = useState("workspace");
  const { data, error } = useLoad<{
    projects: number;
    releases: number;
    runs: number;
    published: number;
    review_count: number;
    status_counts: Record<string, number>;
    recent: Run[];
  }>("/overview?dataset=" + dataset);
  return (
    <>
      <PageHead
        eyebrow="YOUR CLASSIFICATION WORKSPACE"
        title="A clearer picture of every game."
        action={
          <Link className="button primary" to="/analyze">
            <Plus size={18} />
            Analyze a game
          </Link>
        }
      >
        Bring the evidence. Keep the decisions traceable.
      </PageHead>
      <ErrorMessage error={error} />
      <div className="toolbar">
        <div className="segmented">
          <button
            aria-pressed={dataset === "workspace"}
            onClick={() => setDataset("workspace")}
          >
            Workspace
          </button>
          <button
            aria-pressed={dataset === "demo"}
            onClick={() => setDataset("demo")}
          >
            Demo only
          </button>
        </div>
        <span className="muted">
          {dataset === "demo"
            ? "Isolated demonstration records"
            : "Your saved projects and runs"}
        </span>
      </div>
      <div className="stats-row">
        {[
          ["Projects", data?.projects],
          ["Releases", data?.releases],
          ["Analysis runs", data?.runs],
          ["Awaiting review", data?.review_count],
        ].map(([n, v]) => (
          <div key={n}>
            <span>{n}</span>
            <strong>{v ?? "—"}</strong>
          </div>
        ))}
      </div>
      {data && (
        <p className="field-note" role="status">
          Runs: {data.status_counts.completed} completed ·{" "}
          {data.status_counts.partial} partial · {data.status_counts.failed}{" "}
          failed · {data.status_counts.interrupted} interrupted.
        </p>
      )}
      <div className="overview-grid">
        <section className="panel">
          <div className="section-head">
            <h2>Recent analyses</h2>
            <Link to="/catalog">
              View history <ArrowUpRight size={15} />
            </Link>
          </div>
          {data && !data.recent.length ? (
            <Empty title="Your first game starts here">
              <p>
                Add a project and its screenshots or description.
                <br />
                Your saved analyses will appear here.
              </p>
              <Link className="button" to="/analyze">
                Add a project <ArrowRight size={16} />
              </Link>
            </Empty>
          ) : (
            <RunList runs={data?.recent ?? []} />
          )}
        </section>
        <section className="panel evidence-intro">
          <div className="eyebrow">EVIDENCE → UNDERSTANDING</div>
          <h2>
            One primary genre.
            <br />A richer Genome.
          </h2>
          <p>
            Separate a game’s store-facing genre from its visual, mechanical,
            and social attributes.
          </p>
          <div className="mini-flow">
            <span>Identity</span>
            <ArrowRight size={14} />
            <span>Evidence</span>
            <ArrowRight size={14} />
            <span>Review</span>
          </div>
          <Link to="/taxonomy">
            Explore the taxonomy <ArrowUpRight size={16} />
          </Link>
        </section>
      </div>
      <div className="lower-grid">
        <section>
          <h2>What you can bring</h2>
          <div className="capability-lines">
            <div>
              <FileImage />
              <span>
                <strong>Metadata & screenshots</strong>Attributed descriptions
                and up to eight local images.
              </span>
              <Badge>Available</Badge>
            </div>
            <div>
              <Film />
              <span>
                <strong>Short gameplay clips</strong>Local MP4 preprocessing.
                Recognition remains unvalidated.
              </span>
              <Badge tone="amber">Experimental</Badge>
            </div>
          </div>
        </section>
        <section className="measurement-note">
          <span className="eyebrow">MEASURE WHAT MATTERS</span>
          <h2>Is Jev helping?</h2>
          <p>
            Accuracy, savings and total-system speedup are not measured yet.
            Inspect the preserved replay and comparison requirements.
          </p>
          <Link to="/experiments">
            Open Jev Impact <ArrowRight size={16} />
          </Link>
        </section>
      </div>
    </>
  );
}
function RunList({ runs }: { runs: Run[] }) {
  return (
    <div className="run-list">
      {runs.map((r) => (
        <Link to={"/runs/" + r.id} key={r.id}>
          <span className="file-icon">
            <FileImage size={20} />
          </span>
          <span className="grow">
            <strong>
              {r.title} {r.dataset === "demo" && <Badge>Demo</Badge>}
            </strong>
            <small>
              {r.primary_label ?? r.primary_status} · {words(r.platform)}
            </small>
          </span>
          <Badge tone={r.status === "failed" ? "red" : "amber"}>
            {words(r.status)}
          </Badge>
          <ArrowUpRight size={16} />
        </Link>
      ))}
    </div>
  );
}
export function Analyze({ cap }: { cap?: Capabilities }) {
  const navigate = useNavigate();
  const [entry, setEntry] =
    useState<ProjectInput["entry"]>("publisher_project");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      if (files.length > 8) throw new Error("Choose at most eight files.");
      const project = await api<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({
          title: form.get("title"),
          release: form.get("release") || "Unspecified release",
          platform: form.get("platform"),
          entry,
          association_confirmed: form.get("association") === "on",
          description: form.get("description") || "",
          source_label: form.get("source_label") || "User-supplied description",
          reference_url: form.get("reference") || "",
        }),
      });
      for (const file of files)
        await api(
          "/projects/" +
            project.id +
            "/assets?name=" +
            encodeURIComponent(file.name) +
            "&kind=" +
            (file.type.startsWith("video/") ? "video" : "image"),
          { method: "POST", body: file },
        );
      const run = await api<Run>("/runs", {
        method: "POST",
        body: JSON.stringify({
          project_id: project.id,
          mode: "offline",
          idempotency_key: crypto.randomUUID(),
        }),
      });
      navigate("/runs/" + run.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHead
        eyebrow="ANALYZE / NEW PROJECT"
        title="Start with the evidence."
      >
        Save a game or unreleased project. Keep its sources attached.
      </PageHead>
      <ErrorMessage error={error} />
      <form onSubmit={submit} className="analysis-form">
        <div className="panel form-main">
          <div className="entry-tabs" role="group" aria-label="Entry path">
            {(
              [
                ["publisher_project", "Publisher project"],
                ["game_reference", "Game / store reference"],
                ["demo", "Explicit demo"],
              ] as const
            ).map(([v, n]) => (
              <button
                type="button"
                aria-pressed={entry === v}
                key={v}
                onClick={() => setEntry(v)}
              >
                {n}
              </button>
            ))}
          </div>
          <div className="form-section">
            <span className="step">01</span>
            <h2>Identify the subject</h2>
            <div className="form-grid">
              <label>
                Game or project name
                <input
                  name="title"
                  required
                  maxLength={160}
                  placeholder="e.g. Untitled publisher project"
                />
              </label>
              <label>
                Release / edition
                <input
                  name="release"
                  placeholder="e.g. PC preview build"
                  maxLength={160}
                />
              </label>
              <label>
                Platform
                <select name="platform">
                  <option value="pc">PC</option>
                  <option value="console">Console</option>
                  <option value="mobile">Mobile</option>
                  <option value="multiplatform">Multiplatform</option>
                </select>
              </label>
              <label>
                Reference URL (optional)
                <input name="reference" type="url" placeholder="https://…" />
              </label>
            </div>
            <p className="field-note">
              Links are saved references only. No store lookup or video download
              is performed.
            </p>
            {entry === "game_reference" ? (
              <div className="notice">
                A title or store URL is not verified identity. This record will
                need review before evidence can be associated.
              </div>
            ) : (
              <label className="checkbox">
                <input type="checkbox" name="association" required />
                I’m authorized to provide this material and associate it with
                this project.
              </label>
            )}
          </div>
          <div className="form-section">
            <span className="step">02</span>
            <h2>Add evidence</h2>
            <label className="upload-box">
              <Upload size={26} />
              <strong>Choose screenshots or a short clip</strong>
              <span>
                PNG, JPEG, WebP · 5 MiB each
                <br />
                {cap?.video
                  ? "MP4 · 40 MiB, 60 seconds, 1080p maximum"
                  : "Video unavailable: local FFmpeg tools required"}
              </span>
              <input
                type="file"
                aria-label="Evidence files"
                multiple
                accept={
                  cap?.video
                    ? "image/png,image/jpeg,image/webp,video/mp4"
                    : "image/png,image/jpeg,image/webp"
                }
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
            </label>
            {files.length > 0 && (
              <ul className="file-list">
                {files.map((f, i) => (
                  <li key={i}>
                    <FileImage size={16} />
                    {f.name}
                    <span>{(f.size / 1024).toFixed(0)} KB</span>
                  </li>
                ))}
              </ul>
            )}
            <label>
              Source attribution
              <input
                name="source_label"
                placeholder="e.g. Publisher design notes, build 0.3"
                maxLength={200}
              />
            </label>
            <label>
              Source description (optional)
              <textarea
                name="description"
                rows={5}
                maxLength={20000}
                placeholder="Paste an attributed description. Claims remain documentary, not visual observations."
              />
            </label>
          </div>
        </div>
        <aside className="panel submission">
          <span className="eyebrow">BEFORE YOU RUN</span>
          <h2>Offline preparation</h2>
          <Badge tone="amber">No paid inference</Badge>
          <p>
            Uploads are validated, hashed and saved. Clips are sampled locally.
            Text remains an attributed quotation.
          </p>
          <ul className="checklist">
            <li>
              <Check size={16} />
              Durable project and run history
            </li>
            <li>
              <Check size={16} />
              No fabricated classifications
            </li>
            <li>
              <Check size={16} />
              Your evidence stays local
            </li>
          </ul>
          <div className="notice">
            {cap?.live_reason ?? "Loading provider availability…"}
          </div>
          {entry === "demo" && (
            <p>
              <Badge>Demo dataset</Badge> Kept separate from workspace totals.
            </p>
          )}
          <button className="button primary full" disabled={busy || !cap}>
            {busy ? "Saving evidence…" : "Prepare analysis"}
            <ArrowRight size={17} />
          </button>
          <span className="field-note">
            No genre or tag recognition is claimed in offline mode.
          </span>
        </aside>
      </form>
    </>
  );
}
export function CatalogPage() {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") || 1);
  const [tab, setTab] = useState("projects");
  const { data: tax } = useLoad<Taxonomy>("/taxonomy");
  const { data, error } = useLoad<Catalog>("/projects?" + params.toString());
  const { data: runs } = useLoad<Run[]>("/runs");
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.set(key, value);
    next.set("page", "1");
    setParams(next);
  }
  return (
    <>
      <PageHead
        eyebrow="CATALOG & HISTORY"
        title="Find the game. Follow its history."
        action={
          <Link className="button primary" to="/analyze">
            <Plus size={16} />
            Add game
          </Link>
        }
      />
      <ErrorMessage error={error} />
      <div className="segmented">
        <button
          aria-pressed={tab === "projects"}
          onClick={() => setTab("projects")}
        >
          Projects & catalog
        </button>
        <button aria-pressed={tab === "runs"} onClick={() => setTab("runs")}>
          Analysis history
        </button>
      </div>
      {tab === "runs" ? (
        <section className="panel">
          {runs?.length ? (
            <RunList runs={runs} />
          ) : (
            <Empty title="No saved runs">
              <Link to="/analyze">Prepare your first analysis</Link>
            </Empty>
          )}
        </section>
      ) : (
        <>
          <div className="filters">
            <label>
              Search
              <input
                aria-label="Search catalog"
                value={params.get("q") || ""}
                onChange={(e) => filter("q", e.target.value)}
                placeholder="Title or release"
              />
            </label>
            <label>
              Platform
              <select
                onChange={(e) => filter("platform", e.target.value)}
                value={params.get("platform") || ""}
              >
                <option value="">All platforms</option>
                {["pc", "console", "mobile", "multiplatform"].map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </label>
            <label>
              Genre family
              <select
                value={params.get("family") || ""}
                onChange={(e) => filter("family", e.target.value)}
              >
                <option value="">All families</option>
                {tax?.families.map((f) => (
                  <option value={f.id} key={f.id}>
                    {f.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Review
              <select
                value={params.get("review") || ""}
                onChange={(e) => filter("review", e.target.value)}
              >
                <option value="">Any status</option>
                <option value="approved">Approved primary</option>
                <option value="pending">Pending</option>
              </select>
            </label>
            <label>
              Dataset
              <select
                value={params.get("dataset") || "workspace"}
                onChange={(e) => filter("dataset", e.target.value)}
              >
                <option value="workspace">Workspace</option>
                <option value="demo">Demo only</option>
              </select>
            </label>
            <label>
              Sort
              <select
                value={params.get("sort") || "newest"}
                onChange={(e) => filter("sort", e.target.value)}
              >
                <option value="newest">Newest first</option>
                <option value="title">Title A–Z</option>
              </select>
            </label>
          </div>
          <details className="advanced-filters">
            <summary>More filters: genre, attributes, input and date</summary>
            <div className="filters">
              <label>
                Primary genre
                <select
                  value={params.get("genre") || ""}
                  onChange={(e) => filter("genre", e.target.value)}
                >
                  <option value="">Any primary</option>
                  {tax?.families.flatMap((f) =>
                    f.genres.map((g) => (
                      <option value={g.id} key={g.id}>
                        {g.display_name}
                      </option>
                    )),
                  )}
                </select>
              </label>
              <label>
                Reviewed attribute
                <select
                  value={params.get("attribute") || ""}
                  onChange={(e) => filter("attribute", e.target.value)}
                >
                  <option value="">Any attribute</option>
                  {tax?.tags.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Attribute state
                <select
                  value={params.get("state") || "present"}
                  onChange={(e) => filter("state", e.target.value)}
                >
                  <option value="present">Present</option>
                  <option value="absent">Absent</option>
                </select>
              </label>
              <label>
                Input type
                <select
                  value={params.get("input_type") || ""}
                  onChange={(e) => filter("input_type", e.target.value)}
                >
                  <option value="">Any evidence</option>
                  <option value="image">Image</option>
                  <option value="video">Video</option>
                </select>
              </label>
              <label>
                Created on or after
                <input
                  type="date"
                  value={params.get("after") || ""}
                  onChange={(e) => filter("after", e.target.value)}
                />
              </label>
            </div>
          </details>
          <section className="panel">
            <div className="section-head">
              <h2>{data ? data.total + " projects" : "Loading projects…"}</h2>
              <a
                className="button"
                href={
                  "/api/catalog/export?" + params.toString() + "&format=csv"
                }
              >
                Export filtered CSV
              </a>
            </div>
            {data?.items.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Game / release</th>
                      <th>Primary genre</th>
                      <th>Platform</th>
                      <th>Status</th>
                      <th>History</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((p) => (
                      <tr key={p.id}>
                        <td>
                          <strong>{p.title}</strong>
                          <small>{p.release}</small>
                        </td>
                        <td>{p.approved_primary_label ?? "Not assigned"}</td>
                        <td>{words(p.platform)}</td>
                        <td>
                          <Badge
                            tone={p.approved_primary ? "neutral" : "amber"}
                          >
                            {p.approved_primary ? "Approved" : "Needs review"}
                          </Badge>
                        </td>
                        <td>
                          <ProjectHistory project={p} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : data ? (
              <Empty title="No projects match">
                <p>Try a different filter or add your first game.</p>
                <Link to="/analyze">Add a game</Link>
              </Empty>
            ) : (
              <p role="status">Loading catalog…</p>
            )}
          </section>
          <div className="pagination">
            <button
              disabled={page <= 1}
              onClick={() =>
                setParams({
                  ...Object.fromEntries(params),
                  page: String(page - 1),
                })
              }
            >
              Previous
            </button>
            <span>Page {page}</span>
            <button
              disabled={!data || page * data.page_size >= data.total}
              onClick={() =>
                setParams({
                  ...Object.fromEntries(params),
                  page: String(page + 1),
                })
              }
            >
              Next
            </button>
          </div>
        </>
      )}
    </>
  );
}
function ProjectHistory({ project }: { project: Project }) {
  const { data } = useLoad<Run[]>("/runs?project_id=" + project.id);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  return data?.length ? (
    <Link to={"/runs/" + data[0].id}>{project.run_count} runs →</Link>
  ) : (
    <>
      <ErrorMessage error={error} />
      <button
        disabled={!data}
        onClick={async () => {
          try {
            const r = await api<Run>("/runs", {
              method: "POST",
              body: JSON.stringify({
                project_id: project.id,
                mode: "offline",
                idempotency_key: crypto.randomUUID(),
              }),
            });
            navigate("/runs/" + r.id);
          } catch (e) {
            setError((e as Error).message);
          }
        }}
      >
        Prepare run
      </button>
    </>
  );
}
export function ResultPage({ cap }: { cap?: Capabilities }) {
  const { id } = useParams();
  const [r, setRun] = useState<Run>();
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [review, setReview] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const navigate = useNavigate();
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const v = await api<Run>("/runs/" + id);
        if (stopped) return;
        setRun(v);
        if (
          ![
            "completed",
            "partial",
            "failed",
            "cancelled",
            "interrupted",
          ].includes(v.status)
        )
          timer = setTimeout(load, 700);
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      }
    }
    load();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [id]);
  if (!r)
    return (
      <>
        <ErrorMessage error={error} />
        {!error && <p role="status">Loading saved analysis…</p>}
      </>
    );
  const a = r.assets?.find((a) => a.id === selected) ?? r.assets?.[0];
  return (
    <>
      <PageHead
        eyebrow={"ANALYSIS / " + r.id.slice(0, 8)}
        title={r.title}
        action={
          <div className="actions">
            <a
              className="button"
              href={"/api/runs/" + r.id + "/export?format=json"}
            >
              Export JSON
            </a>
            <a
              className="button"
              href={"/api/runs/" + r.id + "/export?format=csv"}
            >
              CSV
            </a>
            <button
              onClick={() => setReview(!review)}
              disabled={cap?.role !== "reviewer"}
            >
              Review / edit
            </button>
          </div>
        }
      >
        {r.release} · {words(r.platform)}
      </PageHead>
      <ErrorMessage error={error} />
      <div className="result-primary">
        <div>
          <div className="eyebrow">STORE-FACING PRIMARY</div>
          <h2>{r.primary_label ?? "Not classified"}</h2>
          <p>{r.primary_status}</p>
        </div>
        <div className="result-badges">
          <Badge tone="amber">{words(r.status)}</Badge>
          <Badge>{words(r.identity_status)}</Badge>
          <Badge>Offline · no recognition</Badge>
          {r.dataset === "demo" && (
            <Badge tone="amber">Demo / UI test data</Badge>
          )}
        </div>
      </div>
      {r.blocker && <div className="notice">{r.blocker}</div>}
      {review && (
        <ReviewEditor
          pid={r.project_id}
          onSaved={() => api<Run>("/runs/" + r.id).then(setRun)}
        />
      )}
      <div className="result-grid">
        <section>
          <div className="section-head">
            <h2>Genome attributes</h2>
            <span className="muted">25 pilot attributes</span>
          </div>
          {Array.from(new Set(r.tags?.map((t) => t.category))).map(
            (category) => (
              <section className="panel tag-group" key={category}>
                <h3>{words(category)}</h3>
                {r.tags
                  ?.filter((t) => t.category === category)
                  .map((t) => (
                    <details key={t.id}>
                      <summary>
                        <span>{t.label}</span>
                        <Badge>
                          {t.state ? words(t.state) : words(t.execution)}
                        </Badge>
                      </summary>
                      {t.human_state && (
                        <p>
                          <Badge>Human review: {words(t.human_state)}</Badge>{" "}
                          Separate from the model answer.
                        </p>
                      )}
                      <p>{t.support_status}</p>
                      <p>
                        Execution: {words(t.execution)}. No model probability is
                        available.
                      </p>
                      {t.probabilities && (
                        <pre>{JSON.stringify(t.probabilities, null, 2)}</pre>
                      )}
                    </details>
                  ))}
              </section>
            ),
          )}
        </section>
        <aside>
          <section className="panel evidence-viewer">
            <div className="section-head">
              <h2>Evidence</h2>
              <Badge>{r.assets?.length ?? 0} assets</Badge>
            </div>
            {a ? (
              <>
                <div className="asset-tabs">
                  {r.assets?.map((x) => (
                    <button
                      aria-pressed={x.id === a.id}
                      key={x.id}
                      onClick={() => setSelected(x.id)}
                    >
                      {x.kind === "video" ? (
                        <Film size={16} />
                      ) : (
                        <FileImage size={16} />
                      )}
                      <span>{x.name}</span>
                    </button>
                  ))}
                </div>
                {a.kind === "video" ? (
                  <video
                    ref={video}
                    key={a.id}
                    src={a.url}
                    controls
                    preload="metadata"
                  />
                ) : (
                  <img
                    className="evidence-image"
                    src={a.url}
                    alt={"Uploaded evidence: " + a.name}
                  />
                )}
                <p className="field-note">
                  {a.width} × {a.height} ·{" "}
                  {a.kind === "video"
                    ? "Experimental ordered windows"
                    : "Still image; timing cannot be established"}
                </p>
                {(a.frames?.length ?? 0) > 0 && (
                  <div className="filmstrip">
                    {a.frames?.map((f, i) => (
                      <button
                        key={i}
                        aria-label={"Seek to " + f.timestamp + " seconds"}
                        onClick={() => {
                          if (video.current)
                            video.current.currentTime = Number(f.timestamp);
                        }}
                      >
                        <img
                          alt={"Sample at " + f.timestamp + " seconds"}
                          src={String(f.url)}
                        />
                        <span>{Number(f.timestamp).toFixed(2)}s</span>
                      </button>
                    ))}
                  </div>
                )}
                <details>
                  <summary>Asset provenance</summary>
                  <p className="mono">SHA-256 {a.sha256}</p>
                  <p>Uploaded context; specific support not yet verified.</p>
                </details>
              </>
            ) : (
              <Empty title="Text-only evidence">
                <p>No images or clips were supplied.</p>
              </Empty>
            )}
            <h3>Attributed observations</h3>
            {r.observations?.length ? (
              r.observations.map((o, i) => (
                <blockquote key={i}>
                  <Badge>{words(String(o.kind))}</Badge>
                  <p>{String(o.text)}</p>
                  <small>Source: {String(o.evidence_id)}</small>
                </blockquote>
              ))
            ) : (
              <p className="muted">
                No visual observation has been made. Upload preparation is not
                model recognition.
              </p>
            )}
          </section>
          <section className="panel trace">
            <h2>Run trace</h2>
            <ol>
              {r.events?.map((e, i) => (
                <li key={i}>
                  <strong>{words(String(e.stage))}</strong>
                  {e.execution === "not_evaluated" && (
                    <Badge>Not evaluated</Badge>
                  )}
                  <small>{new Date(String(e.at)).toLocaleTimeString()}</small>
                </li>
              ))}
            </ol>
            <details>
              <summary>Full available provenance</summary>
              <pre>{JSON.stringify(r.provenance, null, 2)}</pre>
            </details>
            <p className="field-note">
              Local preparation timing is not live pipeline performance.
            </p>
            <button
              onClick={async () => {
                try {
                  const n = await api<Run>("/runs", {
                    method: "POST",
                    body: JSON.stringify({
                      project_id: r.project_id,
                      mode: "offline",
                      idempotency_key: crypto.randomUUID(),
                    }),
                  });
                  navigate("/runs/" + n.id);
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Prepare another run
            </button>
          </section>
          <section className="panel">
            <h2>Review history</h2>
            {r.reviews?.length ? (
              r.reviews.map((v, i) => (
                <p key={i}>
                  <strong>
                    v{String(v.version)} · {String(v.kind)}
                  </strong>
                  <br />
                  {String(v.reason)}
                  <small>
                    {String(v.reviewer)} · {String(v.at)}
                  </small>
                </p>
              ))
            ) : (
              <p>No human corrections recorded.</p>
            )}
          </section>
        </aside>
      </div>
    </>
  );
}
function ReviewEditor({ pid, onSaved }: { pid: string; onSaved: () => void }) {
  const { data: tax } = useLoad<Taxonomy>("/taxonomy");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [kind, setKind] = useState<Review["kind"]>("primary");
  const [version, setVersion] = useState<number>();
  useEffect(() => {
    api<Project>("/projects/" + pid)
      .then((p) => setVersion(p.review_version))
      .catch((e) => setError(e.message));
  }, [pid]);
  return (
    <form
      className="panel review-form"
      onSubmit={async (e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        try {
          if (version === undefined)
            throw new Error("Review snapshot is not loaded");
          await api("/projects/" + pid + "/reviews", {
            method: "POST",
            body: JSON.stringify({
              kind,
              value: f.get("value"),
              property_id: f.get("property_id") || null,
              reason: f.get("reason"),
              expected_version: version,
            }),
          });
          setVersion(version + 1);
          setSaved(true);
          onSaved();
        } catch (e) {
          setError((e as Error).message);
        }
      }}
    >
      <h2>Record an authorized review</h2>
      <p>
        Human decisions are versioned separately from model output and survive
        reanalysis.
      </p>
      <ErrorMessage error={error} />
      <label>
        Decision
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as Review["kind"])}
        >
          <option value="primary">Approve primary genre</option>
          <option value="identity">Associate with this project</option>
          <option value="attribute">Correct attribute</option>
        </select>
      </label>
      {kind === "attribute" && (
        <label>
          Attribute
          <select name="property_id">
            {tax?.tags.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        Approved value
        <select name="value" key={kind} defaultValue="" required>
          <option value="" disabled>
            Choose an explicit decision
          </option>
          {kind === "primary" ? (
            tax?.families.flatMap((f) =>
              f.genres.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.display_name}
                </option>
              )),
            )
          ) : kind === "identity" ? (
            <option value="associated_project">
              Explicit association with this project
            </option>
          ) : (
            [
              "present",
              "absent",
              "insufficient_evidence",
              "conflicting_evidence",
            ].map((s) => (
              <option key={s} value={s}>
                {words(s)}
              </option>
            ))
          )}
        </select>
      </label>
      <label>
        Reason / source verification
        <textarea name="reason" minLength={8} maxLength={2000} required />
      </label>
      <button className="button primary" disabled={version === undefined}>
        Save reviewed decision
      </button>
      {saved && <p role="status">Review saved.</p>}
    </form>
  );
}
export function TaxonomyPage() {
  const { data, error } = useLoad<Taxonomy>("/taxonomy");
  const [q, setQ] = useState("");
  return (
    <>
      <PageHead
        eyebrow="CANONICAL TAXONOMY / V4.1"
        title="One primary. Many dimensions."
      >
        14 families, 100 primary-capable genres, and 25 pilot Genome attributes.
      </PageHead>
      <ErrorMessage error={error} />
      <label className="search-wide">
        Search the taxonomy
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Genre, attribute, or definition"
        />
      </label>
      <div className="taxonomy-grid">
        {data?.families
          .filter((f) =>
            JSON.stringify(f).toLowerCase().includes(q.toLowerCase()),
          )
          .map((f) => (
            <section className="panel" key={f.id}>
              <div className="section-head">
                <h2>{f.display_name}</h2>
                <Badge>{f.genres.length}</Badge>
              </div>
              <p>{f.definition}</p>
              {f.genres
                .filter(
                  (g) =>
                    !q ||
                    JSON.stringify(g).toLowerCase().includes(q.toLowerCase()) ||
                    f.display_name.toLowerCase().includes(q.toLowerCase()),
                )
                .map((g) => (
                  <details key={g.id}>
                    <summary>{g.display_name}</summary>
                    <p>{g.definition}</p>
                    <strong>Include when</strong>
                    <ul>
                      {g.inclusion_criteria.map((v) => (
                        <li key={v}>{v}</li>
                      ))}
                    </ul>
                    <strong>Boundaries</strong>
                    <ul>
                      {g.exclusion_notes.map((v) => (
                        <li key={v}>{v}</li>
                      ))}
                    </ul>
                  </details>
                ))}
            </section>
          ))}
      </div>
      <h2>Genome attributes</h2>
      <p>Discovery dimensions remain separate from the store-facing genre.</p>
      <div className="taxonomy-grid">
        {data?.tags
          .filter((t) =>
            JSON.stringify(t).toLowerCase().includes(q.toLowerCase()),
          )
          .map((t) => (
            <section className="panel" key={t.id}>
              <Badge>{words(t.category)}</Badge>
              <h3>{t.label}</h3>
              <p>{t.definition}</p>
              <small>
                Allowed evidence: {t.allowed_evidence.map(words).join(", ")}
              </small>
            </section>
          ))}
      </div>
    </>
  );
}
export function ReviewPage({ cap }: { cap?: Capabilities }) {
  const [revision, setRevision] = useState(0);
  const { data, error } = useLoad<{
    identity: Project[];
    genre: Project[];
    execution: Run[];
    attributes: Project[];
  }>("/review?revision=" + revision);
  const [tab, setTab] = useState("identity");
  const [pid, setPid] = useState("");
  const [bulk, setBulk] = useState("");
  const [bulkFormat, setBulkFormat] = useState("json");
  const [report, setReport] = useState<unknown>();
  const [bulkError, setBulkError] = useState("");
  if (cap?.role !== "reviewer")
    return (
      <Empty title="Reviewer access required">
        <p>
          The server restricts review mutations to the configured reviewer role.
        </p>
      </Empty>
    );
  return (
    <>
      <PageHead eyebrow="HUMAN REVIEW" title="Resolve the uncertainty.">
        Identity, evidence and execution issues stay in separate queues.
      </PageHead>
      <ErrorMessage error={error} />
      <div className="segmented">
        {["identity", "genre", "execution", "attributes"].map((t) => (
          <button
            key={t}
            aria-pressed={tab === t}
            onClick={() => {
              setTab(t);
              setPid("");
            }}
          >
            {words(t)}
          </button>
        ))}
      </div>
      <section className="panel">
        {tab === "execution" ? (
          <RunList runs={data?.execution ?? []} />
        ) : (
          (data?.[tab as "identity" | "genre" | "attributes"] ?? []).map(
            (p) => (
              <div className="queue-row" key={p.id}>
                <span>
                  <strong>{p.title}</strong>
                  <small>
                    {p.release} · {words(p.identity_status)}
                  </small>
                </span>
                <button onClick={() => setPid(p.id)}>Review</button>
              </div>
            ),
          )
        )}
        {data &&
          (tab === "execution"
            ? data.execution
            : data[tab as "identity" | "genre" | "attributes"]
          ).length === 0 && (
            <Empty title="Queue is clear">
              <p>No records in this review category.</p>
            </Empty>
          )}
      </section>
      {pid && (
        <ReviewEditor
          key={pid}
          pid={pid}
          onSaved={() => {
            setPid("");
            setRevision((v) => v + 1);
          }}
        />
      )}
      <section className="panel">
        <h2>Bulk intake · dry run</h2>
        <p>
          Validate up to 100 project rows. This does not create records or call
          a provider.
        </p>
        <label>
          {bulkFormat.toUpperCase()} manifest
          <textarea
            rows={5}
            value={bulk}
            onChange={(e) => setBulk(e.target.value)}
            placeholder={'[{"title":"Publisher project","platform":"mobile"}]'}
          />
        </label>
        <label>
          Manifest format
          <select
            value={bulkFormat}
            onChange={(e) => setBulkFormat(e.target.value)}
          >
            <option value="json">JSON</option>
            <option value="csv">CSV</option>
          </select>
        </label>
        <ErrorMessage error={bulkError} />
        <button
          onClick={async () => {
            try {
              setReport(
                await api("/bulk/dry-run", {
                  method: "POST",
                  body:
                    bulkFormat === "json"
                      ? JSON.stringify(JSON.parse(bulk))
                      : bulk,
                  headers: {
                    "Content-Type":
                      bulkFormat === "csv" ? "text/csv" : "application/json",
                  },
                }),
              );
              setBulkError("");
            } catch (e) {
              setBulkError((e as Error).message);
            }
          }}
        >
          Validate manifest
        </button>
        {report !== undefined && <pre>{JSON.stringify(report, null, 2)}</pre>}
      </section>
    </>
  );
}
export function SettingsPage({ cap }: { cap?: Capabilities }) {
  return (
    <>
      <PageHead eyebrow="WORKSPACE SETTINGS" title="Know what is enabled." />
      <section className="panel">
        <h2>Private local mode</h2>
        <p>
          User: {cap?.user} · Role: {cap?.role}
        </p>
        <p>
          Server-enforced localhost access. No public deployment or multiuser
          login is configured.
        </p>
        <h3>Providers & spending</h3>
        <Badge tone="amber">Live spending disabled</Badge>
        <p>{cap?.live_reason}</p>
        <dl>
          <dt>Jev key available</dt>
          <dd>
            {cap?.providers?.jev_key_present
              ? "Configured; not spending approval"
              : "Not configured"}
          </dd>
          <dt>Observer key available</dt>
          <dd>
            {cap?.providers?.observer_key_present
              ? "Configured; not spending approval"
              : "Not configured"}
          </dd>
          <dt>Video tools</dt>
          <dd>
            {cap?.video
              ? "Local preprocessing available"
              : "FFmpeg unavailable"}
          </dd>
        </dl>
        <p>
          No credentials are sent to this browser. Configure keys only in the
          server environment after a separate budget decision.
        </p>
      </section>
    </>
  );
}
export function AboutPage() {
  return (
    <>
      <PageHead eyebrow="METHODOLOGY" title="Evidence before conclusions." />
      <section className="panel reading">
        <h2>How GameTagger works</h2>
        <p>
          A verified game or an explicitly associated publisher project supplies
          attributed metadata and permitted media. The Observer describes what
          the material shows. A decision provider interprets those observations
          against the taxonomy. Validation and policy determine what can be
          published.
        </p>
        <h3>Unknown is an answer. Failure is a different condition.</h3>
        <p>
          Present, absent, insufficient evidence and conflicting evidence are
          distinct semantic states. A failed or unasked question has no model
          answer. Not observing a feature never establishes its absence.
        </p>
        <h3>What the evidence can establish</h3>
        <p>
          Metadata is documentary. A still can show rendering, a camera view or
          visible interface text; it cannot establish event timing. Ordered
          clips preserve sequence, but recognition quality and temporal detail
          must be evaluated separately. A menu marked “Survival” is literal
          text, not a genre conclusion.
        </p>
        <h3>Current limits</h3>
        <p>
          This local build prepares media and preserves records without paid
          inference. The descriptions-only historical replay has unverified
          identities and no human truth. Accuracy, calibration, savings and
          end-to-end speedup are not measured.
        </p>
        <Link to="/experiments">Inspect the evidence for Jev’s impact →</Link>
      </section>
    </>
  );
}
