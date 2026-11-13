export type HazardStatus = "suspected" | "confirmed" | "in_clearance" | "released" | "cancelled";
export type HazardType = "SHA" | "CHA";
export type TaskStatus = "planned" | "active" | "suspended" | "completed" | "cancelled";
export type TaskType = "survey" | "technical_survey" | "clearance" | "verification";

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
  release_method: ReleaseMethod;
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
  items_found: number;
}

export interface OrganisationStats {
  organisation: string;
  tasks: number;
  active_tasks: number;
  completed_tasks: number;
  cleared_area_m2: number;
  items_destroyed: number;
}

export interface ActivityItem {
  at: string;
  entity_type: string;
  action: string;
  source: string;
  summary: string;
}

export interface Dashboard {
  region: string | null;
  regions: string[];
  hazard_count: number;
  open_hazard_count: number;
  items_found: number;
  items_destroyed: number;
  hazards_by_status: Record<HazardStatus, number>;
  hazards_by_class: { hazard_class: string; hazard_count: number; area_m2: number }[];
  tasks_by_type: Record<TaskType, number>;
  organisations: OrganisationStats[];
  qa: { inspections: number; passed: number; failed: number; pass_rate: number | null; residual_items: number };
  field_reports: {
    total: number;
    by_status: Record<string, number>;
    by_finding_type: Record<string, number>;
    median_review_hours: number | null;
  };
  data_quality: { errors: number; warnings: number; by_rule: Record<string, number> };
  recent_activity: ActivityItem[];
  outstanding_area_m2: number;
  land_release: LandRelease;
  casualties: Casualties;
  risk_education: RiskEducationSummary;
  top_priorities: Priority[];
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
  bounds?: [number, number, number, number]; // west, south, east, north: fit instead of fly
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

// ---- land release, casualties, risk education, priorities, report -------------------

export type ReleaseMethod = "cancelled" | "reduced" | "cleared";

export interface LandRelease {
  cancelled_m2: number;
  reduced_m2: number;
  cleared_m2: number;
  total_m2: number;
  items_found: number;
  items_destroyed: number;
  by_year: { year: number; cancelled: number; reduced: number; cleared: number; items_destroyed: number }[];
}

export interface Casualties {
  accidents: number;
  casualties: number;
  killed: number;
  injured: number;
  deminers: number;
  by_sex: Record<string, number>;
  by_age_group: Record<string, number>;
  sadd: Record<string, number>;
  by_activity: Record<string, number>;
  by_year: { year: number; accidents: number; killed: number; injured: number }[];
}

export interface RiskEducationSummary {
  sessions: number;
  girls: number;
  boys: number;
  women: number;
  men: number;
  total: number;
  by_year: { year: number; sessions: number; people: number }[];
}

export interface PriorityComponent {
  factor: number;
  value: unknown;
  points: number;
  why: string;
}

export interface Priority {
  rank: number;
  hazard_id: number;
  code: string;
  name: string;
  region: string;
  status: HazardStatus;
  hazard_class: string;
  area_m2: number;
  score: number;
  components: Record<string, PriorityComponent>;
}

export type Sex = "female" | "male" | "unknown";
export type VictimOutcome = "killed" | "injured";
export type AccidentActivity =
  | "farming"
  | "herding"
  | "travelling"
  | "collecting"
  | "playing"
  | "handling"
  | "demining"
  | "other"
  | "unknown";

export interface VictimInput {
  sex: Sex;
  age: number | null;
  outcome: VictimOutcome;
  is_deminer: boolean;
}

export interface Accident {
  id: number;
  code: string;
  occurred_on: string;
  lon: number;
  lat: number;
  region: string | null;
  item_category: ItemCategory | null;
  activity: AccidentActivity;
  description: string;
  hazard_id: number | null;
  hazard_code: string | null;
  field_report_id: number | null;
  recorded_by: string;
  killed: number;
  injured: number;
  victims: (VictimInput & { id: number })[];
}

export interface RiskEducationSession {
  id: number;
  code: string;
  held_on: string;
  lon: number;
  lat: number;
  region: string | null;
  organisation: string;
  girls: number;
  boys: number;
  women: number;
  men: number;
  total: number;
  notes: string | null;
}

export interface RegionSnapshot {
  region: string;
  open_hazards: number;
  outstanding_m2: number;
  cancelled_m2: number;
  reduced_m2: number;
  cleared_m2: number;
}

export interface AnnualReport {
  year: number;
  country: string;
  generated_at: string;
  open_hazards: number;
  outstanding_m2: number;
  regions: RegionSnapshot[];
  land_release: LandRelease;
  casualties: Casualties;
  risk_education: RiskEducationSummary;
  qa: { inspections: number; passed: number; failed: number; pass_rate: number | null; residual_items: number };
}

export interface AdminAreaProps {
  id: number;
  name: string;
  code: string;
  area_m2: number;
  open_hazards: number;
  contaminated_m2: number;
}
