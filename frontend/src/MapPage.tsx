import { useEffect, useMemo, useState } from "react";
import { fetchAudit, fetchHazards, fetchRecords, fetchStats, fetchTasks } from "./api";
import MapView from "./MapView";
import { STATUS_COLOR, STATUS_LABEL, STATUS_ORDER } from "./status";
import type {
  AuditEntry,
  ClearanceRecord,
  HazardCollection,
  HazardProperties,
  HazardStatus,
  Stats,
  Task,
} from "./types";

import { fmtArea } from "./format";

interface TaskWithRecords extends Task {
  records: ClearanceRecord[];
}

function HazardDetail({ hazard }: { hazard: HazardProperties }) {
  const [tasks, setTasks] = useState<TaskWithRecords[] | null>(null);
  const [history, setHistory] = useState<AuditEntry[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    setHistory(null);
    fetchAudit("hazard", hazard.id)
      .then((h) => {
        if (!cancelled) setHistory(h);
      })
      .catch(() => {
        if (!cancelled) setHistory([]);
      });
    return () => {
      cancelled = true;
    };
  }, [hazard.id, hazard.status]);

  useEffect(() => {
    let cancelled = false;
    setTasks(null);
    fetchTasks(hazard.id)
      .then((list) =>
        Promise.all(list.map(async (t) => ({ ...t, records: await fetchRecords(t.id) }))),
      )
      .then((full) => {
        if (!cancelled) setTasks(full);
      })
      .catch(() => {
        if (!cancelled) setTasks([]);
      });
    return () => {
      cancelled = true;
    };
  }, [hazard.id]);

  return (
    <section className="card">
      <h2>{hazard.name}</h2>
      <p className="muted">{hazard.code}</p>
      <dl>
        <dt>Status</dt>
        <dd>
          <span className="dot" style={{ background: STATUS_COLOR[hazard.status] }} />
          {STATUS_LABEL[hazard.status]}
        </dd>
        <dt>Type</dt>
        <dd>{hazard.hazard_type}</dd>
        <dt>Class</dt>
        <dd>{hazard.hazard_class.replace("_", " ")}</dd>
        <dt>Region</dt>
        <dd>{hazard.region}</dd>
        <dt>Area</dt>
        <dd>{fmtArea(hazard.area_m2)}</dd>
      </dl>
      <h3>Tasks</h3>
      {tasks === null && <p className="muted">Loading…</p>}
      {tasks?.length === 0 && <p className="muted">No tasks recorded.</p>}
      {tasks?.map((t) => {
        const cleared = t.records.reduce((sum, r) => sum + r.area_cleared_m2, 0);
        return (
          <div key={t.id} className="task">
            <strong>{t.task_type}</strong> · {t.status}
            <div className="muted">
              {t.code} · {t.organisation}
            </div>
            {t.records.length > 0 && (
              <div className="muted">
                {t.records.length} records · {fmtArea(cleared)} cleared
              </div>
            )}
          </div>
        );
      })}
      <h3>History</h3>
      {history === null && <p className="muted">Loading…</p>}
      {history?.length === 0 && <p className="muted">No changes recorded.</p>}
      {history?.map((entry) => (
        <div key={entry.id} className="history">
          <div>
            <strong>{entry.action}</strong>
            <span className="badge">{entry.source.startsWith("import:") ? "import" : entry.source}</span>
            <span className="muted"> {new Date(entry.created_at).toLocaleString()}</span>
          </div>
          {entry.action === "update" &&
            Object.entries(entry.changes).map(([field, [from, to]]) => (
              <div key={field} className="muted">
                {field}: {String(from)} → {String(to)}
              </div>
            ))}
        </div>
      ))}
    </section>
  );
}

export default function MapPage() {
  const [data, setData] = useState<HazardCollection | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState<Set<HazardStatus>>(new Set(STATUS_ORDER));
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([fetchHazards(), fetchStats()])
      .then(([h, s]) => {
        setData(h);
        setStats(s);
      })
      .catch((e: Error) => setError(e.message));
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

  return (
    <div className="layout">
      <aside className="sidebar">
        <header>
          <h1>Mine Action Core</h1>
          <p className="muted">
            IMSMA-inspired demo · synthetic data for the fictional country of Karvonia
          </p>
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
        </section>

        {selected ? (
          <HazardDetail hazard={selected} />
        ) : (
          <p className="muted">Click a hazard on the map to see its details.</p>
        )}
      </aside>
      <MapView data={data} visible={visible} selectedId={selectedId} onSelect={setSelectedId} />
    </div>
  );
}
