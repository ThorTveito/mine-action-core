import type {
  AuditEntry,
  ClearanceRecord,
  Dashboard,
  HazardCollection,
  ImportOptions,
  ImportReport,
  Stats,
  Task,
} from "./types";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`);
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export const fetchHazards = () => get<HazardCollection>("/hazards/geojson");
export const fetchStats = () => get<Stats>("/stats");
export const fetchDashboard = () => get<Dashboard>("/dashboard");
export const fetchTasks = (hazardId: number) => get<Task[]>(`/tasks?hazard_id=${hazardId}`);
export const fetchRecords = (taskId: number) =>
  get<ClearanceRecord[]>(`/clearance-records?task_id=${taskId}`);
export const fetchAudit = (entityType: string, entityId: number) =>
  get<AuditEntry[]>(`/audit?entity_type=${entityType}&entity_id=${entityId}&limit=20`);

export async function importHazards(file: File, opts: ImportOptions): Promise<ImportReport> {
  const body = new FormData();
  body.append("file", file);
  body.append("source_crs", opts.sourceCrs);
  body.append("dry_run", String(opts.dryRun));
  body.append("on_error", opts.onError);
  body.append("reject_overlaps", String(opts.rejectOverlaps));
  const res = await fetch("/api/imports/hazards", { method: "POST", body });
  if (!res.ok) {
    const detail = (await res.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof detail?.detail === "string" ? detail.detail : `Import failed (${res.status})`);
  }
  return (await res.json()) as ImportReport;
}
