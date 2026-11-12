import { useCallback, useEffect, useState } from "react";
import {
  createInspection,
  fetchAudit,
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
  QaInspection,
  Task,
  TopologyIssue,
} from "./types";

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
  const cleared = task.records.reduce((sum, r) => sum + r.area_cleared_m2, 0);
  const inspectable = task.task_type === "clearance" && ["active", "completed"].includes(task.status);
  return (
    <div className="task">
      <strong>{task.task_type}</strong> · {task.status}
      <div className="muted">
        {task.code} · {task.organisation}
      </div>
      {task.records.length > 0 && (
        <div className="muted">
          {task.records.length} records · {fmtArea(cleared)} cleared
        </div>
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
  const [version, setVersion] = useState(0);

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
            inspections: t.task_type === "clearance" ? await fetchInspections(t.id) : [],
          })),
        ),
      )
      .then((full) => !cancelled && setTasks(full))
      .catch(() => !cancelled && setTasks([]));
    fetchAudit("hazard", hazard.id)
      .then((h) => !cancelled && setHistory(h))
      .catch(() => !cancelled && setHistory([]));
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

      <h3>Tasks, clearance and QA</h3>
      {tasks === null && <p className="muted">Loading…</p>}
      {tasks?.length === 0 && <p className="muted">No tasks recorded.</p>}
      {tasks?.map((t) => <TaskBlock key={t.id} task={t} onChanged={changed} />)}

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
