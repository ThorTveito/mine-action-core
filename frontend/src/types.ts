export type HazardStatus = "suspected" | "confirmed" | "in_clearance" | "released" | "cancelled";
export type HazardType = "SHA" | "CHA";
export type TaskStatus = "planned" | "active" | "suspended" | "completed" | "cancelled";
export type TaskType = "survey" | "clearance" | "verification";

export interface HazardProperties {
  id: number;
  code: string;
  name: string;
  hazard_type: HazardType;
  hazard_class: string;
  status: HazardStatus;
  region: string;
  area_m2: number;
}

export interface HazardFeature {
  type: "Feature";
  id: number;
  geometry: GeoJSON.MultiPolygon;
  properties: HazardProperties;
}

export interface HazardCollection {
  type: "FeatureCollection";
  features: HazardFeature[];
}

export interface Task {
  id: number;
  code: string;
  hazard_id: number;
  task_type: TaskType;
  status: TaskStatus;
  organisation: string;
  planned_start: string | null;
  planned_end: string | null;
  description: string | null;
}

export interface ClearanceRecord {
  id: number;
  task_id: number;
  record_date: string;
  area_cleared_m2: number;
  items_found: number;
  items_destroyed: number;
  team: string;
}

export interface Stats {
  hazard_count: number;
  hazards_by_status: Record<HazardStatus, number>;
  total_area_m2: number;
  released_area_m2: number;
  cleared_area_m2: number;
  open_task_count: number;
  items_destroyed: number;
}

export interface AuditEntry {
  id: number;
  entity_type: string;
  entity_id: number;
  action: "create" | "update" | "delete";
  changes: Record<string, [unknown, unknown]>;
  source: string;
  actor: string;
  created_at: string;
}

export interface RegionProgress {
  region: string;
  hazard_count: number;
  total_area_m2: number;
  remaining_area_m2: number;
  released_area_m2: number;
  cleared_area_m2: number;
}

export interface MonthlyClearance {
  month: string;
  cleared_area_m2: number;
  items_destroyed: number;
}

export interface Dashboard {
  contaminated_area_m2: number;
  remaining_area_m2: number;
  released_area_m2: number;
  cancelled_area_m2: number;
  release_percent: number;
  area_by_status: Record<HazardStatus, number>;
  tasks_by_status: Record<TaskStatus, number>;
  by_region: RegionProgress[];
  monthly_clearance: MonthlyClearance[];
}

export interface ImportIssue {
  code: string;
  message: string;
}

export interface ImportRowReport {
  row: number;
  label: string;
  code: string | null;
  outcome: "accepted" | "rejected";
  action: "create" | "update" | null;
  errors: ImportIssue[];
  warnings: ImportIssue[];
}

export interface ImportReport {
  import_id: string;
  filename: string;
  source_crs: string;
  dry_run: boolean;
  on_error: "skip" | "abort";
  committed: boolean;
  total: number;
  accepted: number;
  rejected: number;
  created: number;
  updated: number;
  warning_count: number;
  rows: ImportRowReport[];
}

export interface ImportOptions {
  sourceCrs: string;
  dryRun: boolean;
  onError: "skip" | "abort";
  rejectOverlaps: boolean;
}

export type Role = "viewer" | "surveyor" | "editor" | "qa_officer" | "admin";
export type Permission =
  | "write"
  | "import"
  | "qa"
  | "release"
  | "delete"
  | "manage_users"
  | "report"
  | "view_reports";

export interface User {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  is_active: boolean;
}

export interface Meta {
  demo_mode: boolean;
  demo_password: string | null;
  demo_users: { username: string; role: Role }[];
}

export interface QaInspection {
  id: number;
  task_id: number;
  inspection_type: "qa" | "qc";
  inspection_date: string;
  inspector: string;
  sample_area_m2: number;
  residual_items_found: number;
  outcome: "pass" | "fail";
  notes: string | null;
}

export interface QaInspectionInput {
  task_id: number;
  inspection_date: string;
  sample_area_m2: number;
  residual_items_found: number;
  outcome: "pass" | "fail";
  notes: string | null;
}

export type Severity = "info" | "warning" | "error";

export interface TopologyIssue {
  rule: string;
  severity: Severity;
  message: string;
  hazard_ids: number[];
  hazard_codes: string[];
  location: GeoJSON.Point | null;
  value: number | null;
}

export interface TopologyReport {
  checked_hazards: number;
  issue_count: number;
  by_severity: Partial<Record<Severity, number>>;
  by_rule: Record<string, number>;
  issues: TopologyIssue[];
}

export interface TopologyCluster {
  hazard_count: number;
  total_area_m2: number;
  shared_boundary_m: number;
  regions: string[];
  status_counts: Record<string, number>;
  members: { id: number; code: string; status: HazardStatus; region: string }[];
}

export interface TopologyClusters {
  cluster_count: number;
  clustered_hazards: number;
  isolated_hazards: number;
  clusters: TopologyCluster[];
}

export interface MapFocus {
  hazardId?: number;
  lon?: number;
  lat?: number;
  nonce: number;
}

export type FindingType = "item_found" | "suspected_area" | "accident" | "other";
export type ItemCategory = "ap_mine" | "av_mine" | "uxo" | "submunition" | "ied" | "unknown";
export type ReportSource = "direct_observation" | "local_informant" | "authority";
export type ReportStatus = "submitted" | "accepted" | "rejected";

export interface FieldReportInput {
  client_id: string;
  observed_at: string;
  finding_type: FindingType;
  item_category: ItemCategory | null;
  quantity: number | null;
  source: ReportSource;
  description: string;
  lon: number;
  lat: number;
  gps_accuracy_m: number | null;
}

export interface FieldReport extends FieldReportInput {
  id: number;
  code: string;
  reported_by: string;
  received_at: string;
  status: ReportStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  hazard_id: number | null;
  hazard_code: string | null;
  region: string | null;
}

export interface NearbyHazard {
  id: number;
  code: string;
  name: string;
  status: HazardStatus;
  region: string;
  distance_m: number;
  contains_point: boolean;
}

export interface ReportDecision {
  report: FieldReport;
  hazard_id: number | null;
  warnings: string[];
}
