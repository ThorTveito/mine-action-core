import { useCallback, useEffect, useState } from "react";
import {
  createInspection,
  createRecord,
  createTask,
  fetchAudit,
  fetchPriorities,
  updateTask,
  fetchInspections,
  fetchRecords,
  fetchTasks,
  fetchTopology,
  setHazardStatus,
} from "./api";
import { useAuth } from "./AuthContext";
import { fmtArea } from "./format";
import { STATUS_COLOR, STATUS_LABEL } from "./status";
import type {
  AuditEntry,
  ClearanceRecord,
  HazardProperties,
  HazardStatus,
  Priority,
  QaInspection,
  ReleaseMethod,
  Task,
  TaskStatus,
  TaskType,
  TopologyIssue,
} from "./types";
import { RELEASE_COLOR, RELEASE_LABEL, RELEASE_ORDER } from "./viz";

export const TASK_LABEL: Record<TaskType, string> = {
  survey: "Non-technical survey",
  technical_survey: "Technical survey",
  clearance: "Clearance",
  verification: "Verification",
};
const RELEASES: Partial<Record<TaskType, ReleaseMethod>> = {
  survey: "cancelled",
  technical_survey: "reduced",
  clearance: "cleared",
};
const TASK_STATUSES: TaskStatus[] = ["planned", "active", "suspended", "completed", "cancelled"];
const ORGANISATIONS = ["Karvonian Demining Authority", "Northgate Clearance", "Delta Mine Action NGO"];

// UI hint mirroring ALLOWED_TRANSITIONS in backend/app/rules.py; the API is the authority.
const NEXT_STATUS: Record<HazardStatus, HazardStatus[]> = {
  suspected: ["confirmed", "cancelled"],
  confirmed: ["in_clearance", "cancelled"],
  in_clearance: ["confirmed", "released"],
  released: [],
  cancelled: [],
};

interface TaskDetail extends Task {
  records: ClearanceRecord[];
  inspections: QaInspection[];
}

const today = () => new Date().toISOString().slice(0, 10);

function StatusControl({ hazard, onChanged }: { hazard: HazardProperties; onChanged: () => void }) {
  const { user, can } = useAuth();
  const options = NEXT_STATUS[hazard.status];
  const [target, setTarget] = useState<HazardStatus | "">("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setTarget("");
    setError(null);
  }, [hazard.id, hazard.status]);

  if (options.length === 0) return <p className="muted">This status is final.</p>;
  if (!user) return <p className="muted">Log in to change the status.</p>;
  if (!can("write") && !can("release")) return <p className="muted">Your role cannot change status.</p>;

  const allowed = (s: HazardStatus) => (s === "released" ? can("release") : can("write"));
  const apply = async () => {
    if (!target) return;
    setBusy(true);
    setError(null);
    try {
      await setHazardStatus(hazard.id, target);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="status-control">
      <select value={target} onChange={(e) => setTarget(e.target.value as HazardStatus | "")}>
        <option value="">Change status…</option>
        {options.map((s) => (
          <option key={s} value={s} disabled={!allowed(s)}>
            {STATUS_LABEL[s]}
            {allowed(s) ? "" : s === "released" ? " (needs QA officer)" : " (needs editor)"}
          </option>
        ))}
      </select>
      <button className="primary" disabled={!target || busy} onClick={apply}>
        Apply
      </button>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function InspectionForm({ task, onSaved }: { task: Task; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [outcome, setOutcome] = useState<"pass" | "fail">("pass");
  const [date, setDate] = useState(today());
  const [sample, setSample] = useState("0");
  const [residual, setResidual] = useState("0");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) {
    return (
      <button className="small" onClick={() => setOpen(true)}>
        + Record inspection
      </button>
    );
  }

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await createInspection({
        task_id: task.id,
        inspection_date: date,
        sample_area_m2: Number(sample) || 0,
        residual_items_found: Number(residual) || 0,
        outcome,
        notes: notes.trim() || null,
      });
      setOpen(false);
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="inline-form">
      <label>
        Outcome
        <select value={outcome} onChange={(e) => setOutcome(e.target.value as "pass" | "fail")}>
          <option value="pass">Pass</option>
          <option value="fail">Fail</option>
        </select>
      </label>
      <label>
        Date
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <label>
        Sample area (m²)
        <input type="number" min="0" value={sample} onChange={(e) => setSample(e.target.value)} />
      </label>
      <label>
        Residual items
        <input type="number" min="0" value={residual} onChange={(e) => setResidual(e.target.value)} />
      </label>
      <label>
        Notes
        <input value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button className="primary small" disabled={busy} onClick={save}>
          Save
        </button>
        <button className="small" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function TaskBlock({ task, onChanged }: { task: TaskDetail; onChanged: () => void }) {
  const { can } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const released = task.records.reduce((sum, r) => sum + r.area_cleared_m2, 0);
  const inspectable =
    ["clearance", "technical_survey"].includes(task.task_type) && ["active", "completed"].includes(task.status);
  const method = RELEASES[task.task_type];
  const setStatus = async (status: TaskStatus) => {
    setError(null);
    try {
      await updateTask(task.id, { status });
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="task">
      <div className="task-head">
        <span>
          <strong>{TASK_LABEL[task.task_type]}</strong>
          <span className="muted"> · {task.code}</span>
        </span>
        {can("write") ? (
          <select className="mini-select" value={task.status} onChange={(e) => void setStatus(e.target.value as TaskStatus)} aria-label="Task status">
            {TASK_STATUSES.map((st) => (
              <option key={st} value={st}>
                {st}
              </option>
            ))}
          </select>
        ) : (
          <span className="badge">{task.status}</span>
        )}
      </div>
      <div className="muted">{task.organisation}</div>
      {error && <p className="error">{error}</p>}
      {task.records.length > 0 && method && (
        <div className="muted">
          <span className="swatch" style={{ background: RELEASE_COLOR[method] }} />
          {task.records.length} records · {fmtArea(released)} {method}
          {task.records.some((r) => r.items_found > 0) &&
            ` · ${task.records.reduce((n, r) => n + r.items_destroyed, 0)} items destroyed`}
        </div>
      )}
      {can("write") && method && ["active", "planned"].includes(task.status) && (
        <ProgressForm task={task} onSaved={onChanged} />
      )}
      {task.inspections.map((i) => (
        <div key={i.id} className="muted">
          <span className={`badge ${i.outcome === "pass" ? "accepted" : "rejected"}`}>{i.outcome}</span>{" "}
          {i.inspection_type.toUpperCase()} {i.inspection_date} by {i.inspector}
          {i.residual_items_found > 0 && ` · ${i.residual_items_found} residual item(s)`}
        </div>
      ))}
      {inspectable && can("qa") && <InspectionForm task={task} onSaved={onChanged} />}
    </div>
  );
}

function ReleaseProgress({ area, tasks }: { area: number; tasks: TaskDetail[] }) {
  const by: Record<ReleaseMethod, number> = { cancelled: 0, reduced: 0, cleared: 0 };
  for (const t of tasks) for (const r of t.records) by[r.release_method] += r.area_cleared_m2;
  const released = by.cancelled + by.reduced + by.cleared;
  if (released === 0) return <p className="muted">No land released yet.</p>;
  return (
    <div>
      <div className="stack small gapped" role="img" aria-label="Land released by method">
        {RELEASE_ORDER.map((m) =>
          by[m] > 0 ? <div key={m} style={{ width: `${(100 * by[m]) / area}%`, background: RELEASE_COLOR[m] }} /> : null,
        )}
      </div>
      <div className="legend-row compact">
        {RELEASE_ORDER.filter((m) => by[m] > 0).map((m) => (
          <span key={m}>
            <span className="swatch" style={{ background: RELEASE_COLOR[m] }} />
            {RELEASE_LABEL[m].split(" (")[0]} {fmtArea(by[m])}
          </span>
        ))}
        <span className="muted">{Math.round((100 * released) / area)}% of {fmtArea(area)}</span>
      </div>
    </div>
  );
}

function PriorityCard({ p }: { p: Priority }) {
  return (
    <div className="priority-card">
      <div>
        <span className="big">{p.score.toFixed(0)}</span>
        <span className="muted"> / 100 priority score</span>
      </div>
      {Object.entries(p.components).map(([k, c]) => (
        <div key={k} className="muted small-line">
          <strong>{c.points.toFixed(1)}</strong> · {c.why}
        </div>
      ))}
    </div>
  );
}

function AddTaskForm({ hazardId, onSaved }: { hazardId: number; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<TaskType>("survey");
  const [org, setOrg] = useState(ORGANISATIONS[0]);
  const [start, setStart] = useState(today());
  const [error, setError] = useState<string | null>(null);
  if (!open)
    return (
      <button className="small" onClick={() => setOpen(true)}>
        + Add task
      </button>
    );
  const save = async () => {
    setError(null);
    try {
      await createTask({ hazard_id: hazardId, task_type: type, organisation: org, planned_start: start, status: "planned" });
      setOpen(false);
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="inline-form">
      <label>
        Task
        <select value={type} onChange={(e) => setType(e.target.value as TaskType)}>
          {(Object.keys(TASK_LABEL) as TaskType[]).map((t) => (
            <option key={t} value={t}>
              {TASK_LABEL[t]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Organisation
        <input list="orgs" value={org} onChange={(e) => setOrg(e.target.value)} />
        <datalist id="orgs">
          {ORGANISATIONS.map((o) => (
            <option key={o} value={o} />
          ))}
        </datalist>
      </label>
      <label>
        Planned start
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button className="primary small" disabled={!org.trim()} onClick={save}>
          Add
        </button>
        <button className="small" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function ProgressForm({ task, onSaved }: { task: Task; onSaved: () => void }) {
  const method = RELEASES[task.task_type];
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(today());
  const [area, setArea] = useState("");
  const [found, setFound] = useState("0");
  const [destroyed, setDestroyed] = useState("0");
  const [team, setTeam] = useState("Team Alpha");
  const [error, setError] = useState<string | null>(null);
  if (!method) return null;
  if (!open)
    return (
      <button className="small" onClick={() => setOpen(true)}>
        + Record land released
      </button>
    );
  const save = async () => {
    setError(null);
    try {
      await createRecord({
        task_id: task.id,
        record_date: date,
        area_cleared_m2: Number(area) || 0,
        items_found: Number(found) || 0,
        items_destroyed: Number(destroyed) || 0,
        team,
      });
      setOpen(false);
      setArea("");
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="inline-form">
      <p className="muted small-line">
        Recorded as <strong>{RELEASE_LABEL[method]}</strong>
      </p>
      <label>
        Date
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <label>
        Area released (m²)
        <input type="number" min="0" inputMode="decimal" value={area} onChange={(e) => setArea(e.target.value)} />
      </label>
      <div className="two">
        <label>
          Items found
          <input type="number" min="0" value={found} onChange={(e) => setFound(e.target.value)} />
        </label>
        <label>
          Destroyed
          <input type="number" min="0" value={destroyed} onChange={(e) => setDestroyed(e.target.value)} />
        </label>
      </div>
      <label>
        Team
        <input value={team} onChange={(e) => setTeam(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button className="primary small" disabled={!area || !team.trim()} onClick={save}>
          Save
        </button>
        <button className="small" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function TopologyList({ issues }: { issues: TopologyIssue[] }) {
  if (issues.length === 0) return <p className="muted">No spatial issues.</p>;
  return (
    <>
      {issues.map((i, idx) => (
        <div key={idx} className={`issue ${i.severity === "error" ? "err" : "warn"}`}>
          <code>{i.rule}</code> {i.message}
        </div>
      ))}
    </>
  );
}

export default function HazardDetail({
  hazard,
  onChanged,
}: {
  hazard: HazardProperties;
  onChanged: () => void;
}) {
  const [tasks, setTasks] = useState<TaskDetail[] | null>(null);
  const [history, setHistory] = useState<AuditEntry[] | null>(null);
  const [issues, setIssues] = useState<TopologyIssue[] | null>(null);
  const [priority, setPriority] = useState<Priority | null>(null);
  const [version, setVersion] = useState(0);
  const { can } = useAuth();

  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  const changed = useCallback(() => {
    refresh();
    onChanged();
  }, [refresh, onChanged]);

  useEffect(() => {
    let cancelled = false;
    setTasks(null);
    setHistory(null);
    setIssues(null);
    fetchTasks(hazard.id)
      .then((list) =>
        Promise.all(
          list.map(async (t) => ({
            ...t,
            records: await fetchRecords(t.id),
            inspections: ["clearance", "technical_survey"].includes(t.task_type) ? await fetchInspections(t.id) : [],
          })),
        ),
      )
      .then((full) => !cancelled && setTasks(full))
      .catch(() => !cancelled && setTasks([]));
    fetchAudit("hazard", hazard.id)
      .then((h) => !cancelled && setHistory(h))
      .catch(() => !cancelled && setHistory([]));
    fetchPriorities({ hazardId: hazard.id })
      .then((p) => !cancelled && setPriority(p[0] ?? null))
      .catch(() => !cancelled && setPriority(null));
    fetchTopology({ hazardId: hazard.id })
      .then((r) => !cancelled && setIssues(r.issues))
      .catch(() => !cancelled && setIssues([]));
    return () => {
      cancelled = true;
    };
  }, [hazard.id, hazard.status, version]);

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
      <StatusControl hazard={hazard} onChanged={changed} />

      {priority && (
        <>
          <h3>Priority</h3>
          <PriorityCard p={priority} />
        </>
      )}

      <h3>Land release</h3>
      {tasks ? <ReleaseProgress area={hazard.area_m2} tasks={tasks} /> : <p className="muted">Loading…</p>}

      <h3>Tasks and QA</h3>
      {tasks === null && <p className="muted">Loading…</p>}
      {tasks?.length === 0 && <p className="muted">No tasks recorded.</p>}
      {tasks?.map((t) => <TaskBlock key={t.id} task={t} onChanged={changed} />)}
      {can("write") && <AddTaskForm hazardId={hazard.id} onSaved={changed} />}

      <h3>Spatial checks</h3>
      {issues === null ? <p className="muted">Checking…</p> : <TopologyList issues={issues} />}

      <h3>History</h3>
      {history === null && <p className="muted">Loading…</p>}
      {history?.length === 0 && <p className="muted">No changes recorded.</p>}
      {history?.map((entry) => (
        <div key={entry.id} className="history">
          <div>
            <strong>{entry.action}</strong> by {entry.actor}
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
