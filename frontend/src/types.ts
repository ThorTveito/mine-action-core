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
