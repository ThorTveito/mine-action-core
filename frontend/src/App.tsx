import { useState } from "react";
import DashboardPage from "./DashboardPage";
import ImportPage from "./ImportPage";
import MapPage from "./MapPage";

type Tab = "map" | "dashboard" | "import";

const TABS: { id: Tab; label: string }[] = [
  { id: "map", label: "Map" },
  { id: "dashboard", label: "Dashboard" },
  { id: "import", label: "Import" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("map");
  return (
    <div className="shell">
      <nav className="topbar">
        <strong>Mine Action Core</strong>
        {TABS.map((t) => (
          <button
            key={t.id}
            className={t.id === tab ? "tab active" : "tab"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
        <span className="muted topbar-note">Synthetic data · fictional country of Karvonia</span>
      </nav>
      <main className="main">
        {tab === "map" && <MapPage />}
        {tab === "dashboard" && <DashboardPage />}
        {tab === "import" && <ImportPage />}
      </main>
    </div>
  );
}
