import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchFieldReportsGeojson, fetchHazards, fetchStats, fetchTopology } from "./api";
import { useAuth } from "./AuthContext";
import HazardDetail from "./HazardDetail";
import MapView from "./MapView";
import { STATUS_COLOR, STATUS_LABEL, STATUS_ORDER } from "./status";
import type {
  HazardCollection,
  HazardStatus,
  MapFocus,
  Stats,
  TopologyIssue,
} from "./types";
import { fmtArea } from "./format";

export default function MapPage({ focus }: { focus: MapFocus | null }) {
  const { user, can } = useAuth();
  const seesReports = can("report") || can("view_reports");
  const [reports, setReports] = useState<GeoJSON.FeatureCollection | null>(null);
  const [showReports, setShowReports] = useState(true);
  const [data, setData] = useState<HazardCollection | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState<Set<HazardStatus>>(new Set(STATUS_ORDER));
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showIssues, setShowIssues] = useState(false);
  const [issues, setIssues] = useState<TopologyIssue[] | null>(null);
  const [terrain3d, setTerrain3d] = useState(false);
  const [exaggeration, setExaggeration] = useState(1.5);

  const load = useCallback(() => {
    Promise.all([fetchHazards(), fetchStats()])
      .then(([h, s]) => {
        setData(h);
        setStats(s);
      })
      .catch((e: Error) => setError(e.message));
    fetchTopology()
      .then((r) => setIssues(r.issues))
      .catch(() => setIssues(null));
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    if (!seesReports) {
      setReports(null);
      return;
    }
    fetchFieldReportsGeojson()
      .then(setReports)
      .catch(() => setReports(null));
  }, [seesReports, user]);

  useEffect(() => {
    if (focus?.hazardId !== undefined) setSelectedId(focus.hazardId);
  }, [focus]);

  const selected = useMemo(
    () => data?.features.find((f) => f.properties.id === selectedId)?.properties ?? null,
    [data, selectedId],
  );

  const toggle = (status: HazardStatus) =>
    setVisible((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });

  const errorCount = issues?.filter((i) => i.severity === "error").length ?? 0;
  const warningCount = issues?.filter((i) => i.severity === "warning").length ?? 0;

  return (
    <div className="layout">
      <aside className="sidebar">
        <header>
          <h1>Mine Action Core</h1>
          <p className="muted">IMSMA-inspired demo · synthetic data for the fictional country of Karvonia</p>
        </header>

        {error && <p className="error">Could not load data: {error}</p>}

        {stats && (
          <section className="card stats">
            <div>
              <span className="big">{stats.hazard_count}</span>
              <span className="muted">hazards</span>
            </div>
            <div>
              <span className="big">{fmtArea(stats.released_area_m2)}</span>
              <span className="muted">released</span>
            </div>
            <div>
              <span className="big">{stats.open_task_count}</span>
              <span className="muted">open tasks</span>
            </div>
            <div>
              <span className="big">{stats.items_destroyed}</span>
              <span className="muted">items destroyed</span>
            </div>
          </section>
        )}

        <section className="card">
          <h3>Status</h3>
          {STATUS_ORDER.map((s) => (
            <label key={s} className="legend">
              <input type="checkbox" checked={visible.has(s)} onChange={() => toggle(s)} />
              <span className="dot" style={{ background: STATUS_COLOR[s] }} />
              {STATUS_LABEL[s]}
              <span className="muted count">{stats?.hazards_by_status[s] ?? ""}</span>
            </label>
          ))}
          <label className="legend topo-toggle">
            <input type="checkbox" checked={showIssues} onChange={(e) => setShowIssues(e.target.checked)} />
            Spatial check issues
            <span className="muted count">
              {issues === null ? "" : `${errorCount} errors · ${warningCount} warnings`}
            </span>
          </label>
          {seesReports && (
            <label className="legend">
              <input type="checkbox" checked={showReports} onChange={(e) => setShowReports(e.target.checked)} />
              <span className="dot" style={{ background: "#7c3aed" }} />
              Field reports
              <span className="muted count">{reports ? reports.features.length : ""}</span>
            </label>
          )}
        </section>

        <section className="card">
          <h3>Terrain</h3>
          <label className="legend">
            <input type="checkbox" checked={terrain3d} onChange={(e) => setTerrain3d(e.target.checked)} />
            3D terrain and relief shading
          </label>
          {terrain3d && (
            <label className="slider">
              <span className="muted">Vertical exaggeration ×{exaggeration.toFixed(1)}</span>
              <input
                type="range"
                min="1"
                max="4"
                step="0.5"
                value={exaggeration}
                onChange={(e) => setExaggeration(Number(e.target.value))}
              />
              <span className="muted">Drag with right mouse (or Ctrl + drag) to tilt and rotate.</span>
            </label>
          )}
        </section>

        {selected ? (
          <HazardDetail hazard={selected} onChanged={load} />
        ) : (
          <p className="muted">Click a hazard on the map to see its details.</p>
        )}
      </aside>
      <MapView
        data={data}
        visible={visible}
        selectedId={selectedId}
        onSelect={setSelectedId}
        issues={showIssues ? issues : null}
        focus={focus}
        terrain={{ enabled: terrain3d, exaggeration }}
        reports={showReports ? reports : null}
      />
    </div>
  );
}
