import { getToken, setToken } from "./auth";
import type {
  Accident,
  AnnualReport,
  AuditEntry,
  ClearanceRecord,
  Dashboard,
  FieldReport,
  FieldReportInput,
  HazardCollection,
  HazardStatus,
  ImportOptions,
  ImportReport,
  Meta,
  NearbyHazard,
  Priority,
  QaInspection,
  QaInspectionInput,
  ReportDecision,
  ReportStatus,
  RiskEducationSession,
  TaskStatus,
  TaskType,
  VictimInput,
  AccidentActivity,
  ItemCategory,
  Stats,
  Task,
  TopologyClusters,
  TopologyReport,
  User,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function detailOf(res: Response): Promise<string> {
  const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg ?? ""}`)
      .join("; ");
  }
  return `Request failed (${res.status})`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    if (res.status === 401 && token) setToken(null); // token expired: drop it
    throw new ApiError(res.status, await detailOf(res));
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// --- auth
export const login = (username: string, password: string) =>
  request<{ access_token: string; user: User }>("/auth/login", {
    method: "POST",
    body: new URLSearchParams({ username, password }),
  });
export const fetchMe = () => request<User>("/auth/me");
export const fetchMeta = () => request<Meta>("/meta");

// --- data
export const fetchHazards = () => request<HazardCollection>("/hazards/geojson");
export const fetchStats = () => request<Stats>("/stats");
export const fetchDashboard = (region?: string) =>
  request<Dashboard>(`/dashboard${region ? `?region=${encodeURIComponent(region)}` : ""}`);
export const fetchTasks = (hazardId: number) => request<Task[]>(`/tasks?hazard_id=${hazardId}`);
export const fetchRecords = (taskId: number) =>
  request<ClearanceRecord[]>(`/clearance-records?task_id=${taskId}`);
export const fetchAudit = (entityType: string, entityId: number) =>
  request<AuditEntry[]>(`/audit?entity_type=${entityType}&entity_id=${entityId}&limit=20`);
export const setHazardStatus = (hazardId: number, status: HazardStatus) =>
  request<unknown>(`/hazards/${hazardId}`, json("PATCH", { status }));

// --- QA
export const fetchInspections = (taskId: number) =>
  request<QaInspection[]>(`/qa-inspections?task_id=${taskId}`);
export const createInspection = (input: QaInspectionInput) =>
  request<QaInspection>("/qa-inspections", json("POST", input));

// --- topology
export const fetchTopology = (opts: { hazardId?: number; gapToleranceM?: number } = {}) => {
  const q = new URLSearchParams();
  if (opts.hazardId !== undefined) q.set("hazard_id", String(opts.hazardId));
  if (opts.gapToleranceM !== undefined) q.set("gap_tolerance_m", String(opts.gapToleranceM));
  return request<TopologyReport>(`/topology/check?${q}`);
};
export const fetchClusters = () => request<TopologyClusters>("/topology/clusters");

// --- import
export function importHazards(file: File, opts: ImportOptions): Promise<ImportReport> {
  const body = new FormData();
  body.append("file", file);
  body.append("source_crs", opts.sourceCrs);
  body.append("dry_run", String(opts.dryRun));
  body.append("on_error", opts.onError);
  body.append("reject_overlaps", String(opts.rejectOverlaps));
  return request<ImportReport>("/imports/hazards", { method: "POST", body });
}

// --- field reports
export const createFieldReport = (input: FieldReportInput) =>
  request<FieldReport>("/field-reports", json("POST", input));
export const fetchFieldReports = (status?: ReportStatus) =>
  request<FieldReport[]>(`/field-reports${status ? `?status=${status}` : ""}`);
export const fetchFieldReportsGeojson = () =>
  request<GeoJSON.FeatureCollection>("/field-reports/geojson");
export const fetchNearby = (reportId: number, radiusM = 500) =>
  request<NearbyHazard[]>(`/field-reports/${reportId}/nearby?radius_m=${radiusM}`);
export const acceptReport = (
  reportId: number,
  body: {
    mode: "new_hazard" | "link" | "accident";
    hazard_id?: number;
    radius_m?: number;
    name?: string;
    victims?: VictimInput[];
    activity?: AccidentActivity;
  },
) => request<ReportDecision>(`/field-reports/${reportId}/accept`, json("POST", body));
export const rejectReport = (reportId: number, reason: string) =>
  request<ReportDecision>(`/field-reports/${reportId}/reject`, json("POST", { reason }));

// --- tasks and land release
export const createTask = (body: {
  hazard_id: number;
  task_type: TaskType;
  organisation: string;
  status?: TaskStatus;
  planned_start?: string | null;
  planned_end?: string | null;
}) => request<Task>("/tasks", json("POST", body));
export const updateTask = (taskId: number, body: { status?: TaskStatus }) =>
  request<Task>(`/tasks/${taskId}`, json("PATCH", body));
export const createRecord = (body: {
  task_id: number;
  record_date: string;
  area_cleared_m2: number;
  items_found: number;
  items_destroyed: number;
  team: string;
  notes?: string | null;
}) => request<ClearanceRecord>("/clearance-records", json("POST", body));

// --- priorities, areas, report
export const fetchPriorities = (opts: { region?: string; hazardId?: number } = {}) => {
  const q = new URLSearchParams();
  if (opts.region) q.set("region", opts.region);
  if (opts.hazardId !== undefined) q.set("hazard_id", String(opts.hazardId));
  return request<Priority[]>(`/priorities?${q}`);
};
export const fetchAdminAreas = () => request<GeoJSON.FeatureCollection>("/admin-areas");
export const fetchAnnualReport = (year: number) => request<AnnualReport>(`/reports/annual?year=${year}`);

// --- accidents and risk education
export const fetchAccidents = () => request<Accident[]>("/accidents");
export const fetchAccidentsGeojson = () => request<GeoJSON.FeatureCollection>("/accidents/geojson");
export const createAccident = (body: {
  occurred_on: string;
  lon: number;
  lat: number;
  item_category: ItemCategory | null;
  activity: AccidentActivity;
  description: string;
  victims: VictimInput[];
}) => request<Accident>("/accidents", json("POST", body));
export const fetchSessions = () => request<RiskEducationSession[]>("/risk-education");
export const createSession = (body: {
  held_on: string;
  lon: number;
  lat: number;
  organisation: string;
  girls: number;
  boys: number;
  women: number;
  men: number;
  notes: string | null;
}) => request<RiskEducationSession>("/risk-education", json("POST", body));
