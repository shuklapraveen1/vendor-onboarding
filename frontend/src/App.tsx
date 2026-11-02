import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  CircleHelp,
  Cpu,
  Database,
  FilePlus2,
  LayoutDashboard,
  Mails,
  Menu,
  ShieldAlert,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import { LogoMark, ThemeToggle } from "./components/brand";
import { UnpluggedIllustration } from "./components/illustrations";
import { EmptyState } from "./components/scenes";
import { ConfigContext, usePolling } from "./lib";
import Dashboard from "./pages/Dashboard";
import HowItWorks from "./pages/HowItWorks";
import NewSubmission from "./pages/NewSubmission";
import Outbox from "./pages/Outbox";
import Portal from "./pages/Portal";
import ReviewQueue from "./pages/ReviewQueue";
import SubmissionDetail from "./pages/SubmissionDetail";
import Vendors from "./pages/Vendors";
import type { AppConfig } from "./types";

interface NavDef {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  badge?: number;
}

function Shell({ config }: { config: AppConfig }) {
  const queue = usePolling(() => api.stats(), 4000);
  const inReview = queue.data?.by_status.PENDING_REVIEW ?? 0;
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMenuOpen(false);
    window.scrollTo({ top: 0 });
  }, [location.pathname]);

  const nav: NavDef[] = [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
    { to: "/new", label: "New submission", icon: FilePlus2 },
    { to: "/review", label: "Review queue", icon: ShieldAlert, badge: inReview },
    { to: "/outbox", label: "Outbox", icon: Mails },
    { to: "/vendors", label: "Vendor master", icon: Database },
    { to: "/how-it-works", label: "How it works", icon: CircleHelp },
  ];

  return (
    <div className={`shell ${menuOpen ? "menu-open" : ""}`}>
      <div className="mobile-bar">
        <Link to="/" className="brand-inline"><LogoMark size={30} /> <strong>VendorGate</strong></Link>
        <div className="row gap">
          <ThemeToggle compact />
          <button type="button" className="icon-btn" onClick={() => setMenuOpen((o) => !o)} aria-label="Toggle menu">
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      <aside className="sidebar">
        <Link to="/" className="brand">
          <LogoMark />
          <div>
            <strong>VendorGate</strong>
            <span>Vendor onboarding, automated</span>
          </div>
        </Link>
        <nav className="nav">
          <span className="nav-section">Workspace</span>
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
              {({ isActive }) => (
                <>
                  {isActive && <motion.span layoutId="nav-active" className="nav-active-bg" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
                  <span className="nav-icon"><n.icon size={18} strokeWidth={2} /></span>
                  <span className="nav-label">{n.label}</span>
                  <AnimatePresence>
                    {n.badge ? (
                      <motion.span
                        key={n.badge}
                        className="nav-badge"
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        exit={{ scale: 0 }}
                        transition={{ type: "spring", stiffness: 600, damping: 20 }}
                      >
                        {n.badge}
                      </motion.span>
                    ) : null}
                  </AnimatePresence>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className={`ai-mode ${config.llm.enabled ? "on" : "off"}`}>
            <span className="ai-icon">{config.llm.enabled ? <Bot size={16} /> : <Cpu size={16} />}</span>
            <div>
              <strong>{config.llm.enabled ? "AI assist on" : "Rules only"}</strong>
              <small>{config.llm.enabled ? `${config.llm.provider} · ${config.llm.model}` : "Deterministic parsers, fully offline"}</small>
            </div>
            <span className="ai-dot" />
          </div>
          <ThemeToggle />
          <small className="sidebar-buyer">Buyer · {config.buyer}</small>
        </div>
      </aside>
      <div className="scrim" onClick={() => setMenuOpen(false)} aria-hidden />

      <main className="content">
        <div key={location.pathname} className="page-enter">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

function NotFound() {
  return (
    <div className="page">
      <EmptyState scene="not-found" title="Page not found" action={<Link to="/" className="btn btn-primary">Back to dashboard</Link>}>
        That address doesn't match anything in VendorGate.
      </EmptyState>
    </div>
  );
}

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setError(null);
    api.config().then(setConfig).catch((e: Error) => setError(e.message));
  }, [attempt]);

  if (error) {
    return (
      <div className="boot">
        <div className="boot-card a-rise">
          <UnpluggedIllustration />
          <h2>Can't reach the backend</h2>
          <p className="muted">{error}</p>
          <p className="small muted">
            Start it with <code>./start.sh</code> (or <code>uvicorn app.main:app --port 8000</code> from <code>backend/</code>).
          </p>
          <button className="btn btn-primary" onClick={() => setAttempt((a) => a + 1)}>Try again</button>
        </div>
      </div>
    );
  }
  if (!config) {
    return (
      <div className="boot">
        <div className="boot-loader a-pop">
          <div className="boot-logo"><LogoMark size={56} /></div>
          <span className="muted">Starting VendorGate…</span>
        </div>
      </div>
    );
  }

  return (
    <ConfigContext.Provider value={config}>
      <Routes>
        <Route path="/portal/:token" element={<Portal />} />
        <Route element={<Shell config={config} />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={<NewSubmission />} />
          <Route path="/submissions/:id" element={<SubmissionDetail />} />
          <Route path="/review" element={<ReviewQueue />} />
          <Route path="/outbox" element={<Outbox />} />
          <Route path="/vendors" element={<Vendors />} />
          <Route path="/how-it-works" element={<HowItWorks />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </ConfigContext.Provider>
  );
}
