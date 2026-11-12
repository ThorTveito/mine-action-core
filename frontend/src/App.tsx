import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { AuthProvider, useAuth } from "./AuthContext";
import ErrorBoundary from "./ErrorBoundary";
import LoginBar from "./LoginBar";
import type { MapFocus } from "./types";

// Each tab is its own chunk, so a field user on a slow connection does not download the map
// engine just to send a report.
const MapPage = lazy(() => import("./MapPage"));
const DashboardPage = lazy(() => import("./DashboardPage"));
const TopologyPage = lazy(() => import("./TopologyPage"));
const ImportPage = lazy(() => import("./ImportPage"));
const FieldPage = lazy(() => import("./FieldPage"));

type Tab = "map" | "dashboard" | "topology" | "import" | "field";

const TABS: { id: Tab; label: string }[] = [
  { id: "map", label: "Map" },
  { id: "field", label: "Field reports" },
  { id: "dashboard", label: "Dashboard" },
  { id: "topology", label: "Spatial checks" },
  { id: "import", label: "Import" },
];

function Shell() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("map");
  const [focus, setFocus] = useState<MapFocus | null>(null);

  // Field surveyors land on the report form; that is all they need in the field.
  useEffect(() => {
    if (user?.role === "surveyor") setTab("field");
  }, [user]);

  const showOnMap = useCallback((target: Omit<MapFocus, "nonce">) => {
    setFocus({ ...target, nonce: Date.now() });
    setTab("map");
  }, []);

  return (
    <div className="shell">
      <nav className="topbar">
        <strong className="brand">Mine Action Core</strong>
        <div className="tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={t.id === tab}
              className={t.id === tab ? "tab active" : "tab"}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <span className="muted topbar-note">Synthetic data · fictional Karvonia</span>
        <LoginBar />
      </nav>
      <main className="main">
        <ErrorBoundary resetKey={tab}>
          <Suspense fallback={<div className="page"><p className="muted">Loading…</p></div>}>
            {tab === "map" && <MapPage focus={focus} />}
            {tab === "field" && <FieldPage key={user?.username ?? "anonymous"} onShow={showOnMap} />}
            {tab === "dashboard" && <DashboardPage />}
            {tab === "topology" && <TopologyPage onShow={showOnMap} />}
            {tab === "import" && <ImportPage />}
          </Suspense>
        </ErrorBoundary>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
