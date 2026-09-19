import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  ArrowUpRight,
  BookOpen,
  Boxes,
  ChartNoAxesCombined,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  Layers,
  LayoutDashboard,
  Menu,
  Plus,
  Route as RouteIcon,
  Settings,
  X,
} from "lucide-react";
import { api, type Capabilities } from "./api";
import {
  Overview,
  Analyze,
  CatalogPage,
  ResultPage,
  TaxonomyPage,
  ReviewPage,
  SettingsPage,
  AboutPage,
} from "./pages";
import { Experiments, Roadmap } from "./experiments";
const main = [
  ["/", "Overview", LayoutDashboard],
  ["/analyze", "Analyze", Plus],
  ["/catalog", "Catalog", Boxes],
  ["/taxonomy", "Taxonomy", BookOpen],
] as const;
const admin = [
  ["/review", "Review", ClipboardCheck],
  ["/experiments", "Jev Impact", ChartNoAxesCombined],
  ["/roadmap", "Roadmap", RouteIcon],
  ["/settings", "Settings", Settings],
] as const;
export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="empty">
      <Layers size={28} />
      <h3>{title}</h3>
      <div>{children}</div>
    </div>
  );
}
export function ErrorMessage({ error }: { error: string }) {
  return error ? (
    <div className="error" role="alert">
      {error}
    </div>
  ) : null;
}
export function PageHead({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      {action}
    </div>
  );
}
export default function App() {
  const [cap, setCap] = useState<Capabilities>();
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [narrow, setNarrow] = useState(
    window.matchMedia("(max-width: 900px)").matches,
  );
  const closeButton = useRef<HTMLButtonElement>(null);
  const openButton = useRef<HTMLButtonElement>(null);
  function closeMenu() {
    setOpen(false);
    openButton.current?.focus();
  }
  useEffect(() => {
    const media = window.matchMedia("(max-width: 900px)");
    const change = () => setNarrow(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (open && narrow) closeButton.current?.focus();
  }, [open, narrow]);
  const location = useLocation();
  useEffect(() => {
    api<Capabilities>("/capabilities")
      .then(setCap)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);
  const current =
    [...main, ...admin].find(([p]) => p === location.pathname)?.[1] ??
    "Analysis detail";
  return (
    <div className="app">
      <a href="#main" className="skip">
        Skip to content
      </a>
      <aside
        className={open ? "sidebar open" : "sidebar"}
        inert={narrow && !open}
        role={narrow && open ? "dialog" : undefined}
        aria-modal={narrow && open ? true : undefined}
        aria-label="Navigation"
        onKeyDown={(e) => {
          if (!narrow || !open) return;
          if (e.key === "Escape") closeMenu();
          if (e.key === "Tab") {
            const items = Array.from(
              e.currentTarget.querySelectorAll<HTMLElement>("a,button"),
            );
            const first = items[0],
              last = items.at(-1);
            if (e.shiftKey && document.activeElement === first) {
              e.preventDefault();
              last?.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
              e.preventDefault();
              first.focus();
            }
          }
        }}
      >
        <Link to="/" className="brand">
          <span className="mark">
            <Layers size={22} />
          </span>
          GameTagger<span className="brand-dot">.</span>
        </Link>
        <button
          className="mobile close icon-button"
          ref={closeButton}
          onClick={closeMenu}
          aria-label="Close menu"
        >
          <X />
        </button>
        <div className="workspace-name">
          Personal workspace <Badge>LOCAL</Badge>
        </div>
        <nav aria-label="Main navigation">
          {main.map(([p, n, Icon]) => (
            <NavLink key={p} end={p === "/"} to={p}>
              <Icon size={19} />
              {n}
            </NavLink>
          ))}
        </nav>
        <div className="nav-label">WORKSPACE TOOLS</div>
        <nav aria-label="Workspace tools">
          {admin.map(([p, n, Icon]) => (
            <NavLink key={p} to={p}>
              <Icon size={19} />
              {n}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="taxonomy-stamp">
            A shared language for games
            <br />
            <strong>Taxonomy v4.1</strong>
          </div>
          <Link to="/about">
            <CircleHelp size={16} /> Methodology & help{" "}
            <ArrowUpRight size={14} />
          </Link>
        </div>
      </aside>
      {open && (
        <button
          className="scrim"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        />
      )}
      <div className="workspace" inert={narrow && open}>
        <header>
          <button
            className="mobile icon-button"
            ref={openButton}
            aria-expanded={open}
            aria-label="Open menu"
            onClick={() => setOpen(true)}
          >
            <Menu />
          </button>
          <div className="breadcrumb">
            <span className="workspace-label">Workspace</span>{" "}
            <ChevronRight size={14} />
            <strong>{current}</strong>
          </div>
          <div className="header-status">
            <span className={cap ? "status-dot" : "status-dot offline"} />
            <span className="status-long">
              {cap ? "Local API connected" : "API unavailable"}
            </span>
            <span className="status-short">
              {cap ? "API ready" : "API offline"}
            </span>
            <span className="header-divider" />
            <Badge tone="amber">Live spend disabled</Badge>
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          <ErrorMessage error={error} />
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/analyze" element={<Analyze cap={cap} />} />
            <Route path="/catalog" element={<CatalogPage />} />
            <Route path="/runs/:id" element={<ResultPage cap={cap} />} />
            <Route path="/taxonomy" element={<TaxonomyPage />} />
            <Route path="/review" element={<ReviewPage cap={cap} />} />
            <Route path="/experiments" element={<Experiments />} />
            <Route path="/roadmap" element={<Roadmap />} />
            <Route path="/settings" element={<SettingsPage cap={cap} />} />
            <Route path="/about" element={<AboutPage />} />
            <Route
              path="*"
              element={
                <Empty title="Page not found">
                  <Link to="/">Return to overview</Link>
                </Empty>
              }
            />
          </Routes>
        </main>
        <footer>
          <span>GameTagger · Evidence before conclusions</span>
          <Link to="/about">Methodology</Link>
          <span>PC / Console / Mobile</span>
        </footer>
      </div>
    </div>
  );
}
