import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { AuthProvider, useAuth } from "./AuthContext";
import ErrorBoundary from "./ErrorBoundary";
import LoginBar from "./LoginBar";
import type { MapFocus, Permission } from "./types";

// Each tab is its own chunk, so a field user on a slow connection does not download the map
// engine just to send a report.
const MapPage = lazy(() => import("./MapPage"));
const DashboardPage = lazy(() => import("./DashboardPage"));
const TopologyPage = lazy(() => import("./TopologyPage"));
const ImportPage = lazy(() => import("./ImportPage"));
const FieldPage = lazy(() => import("./FieldPage"));
const CasualtiesPage = lazy(() => import("./CasualtiesPage"));
const ReportPage = lazy(() => import("./ReportPage"));

type Tab = "map" | "dashboard" | "topology" | "import" | "field" | "casualties" | "report";

// Tabs a role cannot use are hidden; the API enforces access either way.
const TABS: { id: Tab; label: string; visible: (can: (p: Permission) => boolean) => boolean }[] = [
  { id: "map", label: "Map", visible: () => true },
  { id: "dashboard", label: "Dashboard", visible: () => true },
  { id: "field", label: "Field reports", visible: (can) => can("report") || can("view_reports") },
  { id: "casualties", label: "Accidents & EORE", visible: (can) => can("view_reports") },
  { id: "topology", label: "Spatial checks", visible: () => true },
  { id: "import", label: "Import", visible: (can) => can("import") },
  { id: "report", label: "Annual report", visible: () => true },
];

function Shell() {
  const { user, can } = useAuth();
  const tabs = TABS.filter((t) => t.visible(can));
  const [tab, setTab] = useState<Tab>("map");
  const [focus, setFocus] = useState<MapFocus | null>(null);

  // Field surveyors land on the report form; that is all they need in the field.
  useEffect(() => {
    if (user?.role === "surveyor") setTab("field");
  }, [user]);

  // Logging out (or switching role) must not leave you on a tab you can no longer see.
  useEffect(() => {
    if (!tabs.some((t) => t.id === tab)) setTab("map");
  }, [tabs, tab]);

  const showOnMap = useCallback((target: Omit<MapFocus, "nonce">) => {
    setFocus({ ...target, nonce: Date.now() });
    setTab("map");
  }, []);

  return (
    <div className="shell">
      <nav className="topbar">
        <strong className="brand">Mine Action Core</strong>
        <div className="tabs" role="tablist">
          {tabs.map((t) => (
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
            {tab === "dashboard" && (
              <DashboardPage onOpenChecks={() => setTab("topology")} onOpenHazard={(id) => showOnMap({ hazardId: id })} />
            )}
            {tab === "topology" && <TopologyPage onShow={showOnMap} />}
            {tab === "import" && <ImportPage />}
            {tab === "casualties" && <CasualtiesPage onShow={showOnMap} />}
            {tab === "report" && <ReportPage />}
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
