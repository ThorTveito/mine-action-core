import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchAccidentsGeojson,
  fetchAdminAreas,
  fetchFieldReportsGeojson,
  fetchHazards,
  fetchPriorities,
  fetchStats,
  fetchTopology,
} from "./api";
import { useAuth } from "./AuthContext";
import HazardDetail from "./HazardDetail";
import ItemList, { bboxOf } from "./ItemList";
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
  const [mapFocus, setMapFocus] = useState<MapFocus | null>(focus);
  const [view, setView] = useState<[number, number, number, number] | null>(null);
  const [areas, setAreas] = useState<GeoJSON.FeatureCollection | null>(null);
  const [showAreas, setShowAreas] = useState(true);
  const [accidents, setAccidents] = useState<GeoJSON.FeatureCollection | null>(null);
  const [showAccidents, setShowAccidents] = useState(false);
  const [scores, setScores] = useState<Map<number, number>>(new Map());
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
    fetchPriorities()
      .then((ps) => setScores(new Map(ps.map((p) => [p.hazard_id, p.score]))))
      .catch(() => setScores(new Map()));
  }, []);

  useEffect(() => {
    fetchAdminAreas()
      .then(setAreas)
      .catch(() => setAreas(null));
  }, []);

  useEffect(load, [load]);

  const staff = can("view_reports");
  useEffect(() => {
    if (!staff) {
      setAccidents(null);
      return;
    }
    fetchAccidentsGeojson()
      .then(setAccidents)
      .catch(() => setAccidents(null));
  }, [staff, user]);

  // A focus that names only a hazard (e.g. from the dashboard) zooms to that hazard's extent.
  useEffect(() => {
    if (!focus || focus.hazardId === undefined || focus.bounds || focus.lon !== undefined || !data) return;
    const f = data.features.find((x) => x.properties.id === focus.hazardId);
    if (f) setMapFocus({ ...focus, bounds: bboxOf(f.geometry.coordinates) });
  }, [focus, data]);

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
    setMapFocus(focus);
  }, [focus]);

  const pick = useCallback((target: Omit<MapFocus, "nonce">) => {
    if (target.hazardId !== undefined) setSelectedId(target.hazardId);
    setMapFocus({ ...target, nonce: Date.now() });
  }, []);

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
          <label className="legend">
            <input type="checkbox" checked={showAreas} onChange={(e) => setShowAreas(e.target.checked)} />
            <span className="line-key" />
            Administrative boundaries
          </label>
          {staff && (
            <label className="legend">
              <input type="checkbox" checked={showAccidents} onChange={(e) => setShowAccidents(e.target.checked)} />
              <span className="dot" style={{ background: "#eb6834" }} />
              Accidents
              <span className="muted count">{accidents ? accidents.features.length : ""}</span>
            </label>
          )}
          {seesReports && (
            <label className="legend">
              <input type="checkbox" checked={showReports} onChange={(e) => setShowReports(e.target.checked)} />
              <span className="dot" style={{ background: "#7c3aed" }} />
              Field reports
              <span className="muted count">{reports ? reports.features.length : ""}</span>
            </label>
          )}
        </section>


        {selected ? (
          <>
            <button className="link back" onClick={() => setSelectedId(null)}>
              ← Back to the list
            </button>
            <HazardDetail hazard={selected} onChanged={load} />
          </>
        ) : (
          <ItemList
            hazards={data}
            reports={seesReports ? reports : null}
            visible={visible}
            view={view}
            selectedId={selectedId}
            onPick={pick}
            scores={scores}
          />
        )}

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
      </aside>
      <MapView
        data={data}
        visible={visible}
        selectedId={selectedId}
        onSelect={setSelectedId}
        issues={showIssues ? issues : null}
        focus={mapFocus}
        onViewChange={setView}
        terrain={{ enabled: terrain3d, exaggeration }}
        reports={showReports ? reports : null}
        areas={showAreas ? areas : null}
        accidents={showAccidents ? accidents : null}
      />
    </div>
  );
}
