export type Role = "super_admin" | "admin" | "user";
export type JobType = "lock" | "unlock";
export type JobStatus =
  | "draft"
  | "validating"
  | "awaiting_mapping_confirmation"
  | "ready"
  | "queued"
  | "running"
  | "waiting_due_to_rate_limit"
  | "cancel_requested"
  | "cancelled"
  | "completed"
  | "completed_with_errors"
  | "failed";
export type MappingConfidence = "high" | "confirm" | "not_found";
export type MappingStatus = "inferred" | "confirmed" | "stale";
export type JobActionKind = "process_cached" | "process" | "download" | "link";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  is_two_factor_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AuthSession {
  id: string;
  expires_at: string;
  created_at: string;
  last_seen_at: string | null;
}

export interface SessionEnvelope {
  user: AuthUser;
  session: AuthSession;
}

export interface WorkspaceSummary {
  current_user: AuthUser;
  permissions: {
    can_manage_users: boolean;
    can_manage_admins: boolean;
  };
  stats: {
    users: number;
    super_admins: number;
    active_sessions: number;
    jobs: number;
    reports: number;
    mappings: number;
    audit_events: number;
  };
}

export interface JobProgress {
  percent: number;
  summary: string;
  detail: string;
  message: string | null;
  wait_message: string | null;
  wait_seconds_remaining: number | null;
  mode: string;
  rate_limit_per_minute: number;
}

export interface JobListItem {
  id: string;
  job_type: JobType;
  status: JobStatus;
  project_id: string | null;
  project_title: string | null;
  request_file_name: string | null;
  queries_file_name: string | null;
  host_label: string;
  total_rows: number;
  processed_rows: number;
  locked_rows: number;
  unlocked_rows: number;
  ignored_rows: number;
  blocked_rows: number;
  failed_rows: number;
  review_count: number;
  progress: JobProgress;
  report_id: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  status_label: string;
  status_tone: string;
  action_kind: JobActionKind | null;
  action_label: string | null;
  action_hint: string;
  cancel_label: string | null;
  continue_label: string | null;
  remap_label: string | null;
  launch_mode: string | null;
}

export interface JobsList {
  items: JobListItem[];
  has_active_jobs: boolean;
}

export interface MappingReviewItem {
  instrument_name: string;
  instrument_label: string | null;
  confidence: MappingConfidence | null;
  mapping_status: MappingStatus | null;
  form_complete_field_name: string | null;
  status_field_name: string | null;
  lock_date_field_name: string | null;
  suggested_status_field_name: string | null;
  suggested_date_field_name: string | null;
  suggested_status_lock_value: string | null;
  suggested_date_format: string | null;
  requires_confirmation: boolean;
}

export interface MappingReview {
  job_id: string | null;
  project_id: string | null;
  project_title: string | null;
  host_label: string | null;
  refresh_decision_pending: boolean;
  confirmed_mapping_count: number;
  rows: MappingReviewItem[];
}

export interface MappingFieldOption {
  field_name: string;
  field_label: string | null;
  field_type: string;
  validation_type: string | null;
}

export interface MappingFieldCandidate {
  field_name: string;
  field_label: string | null;
  field_type: string;
  lock_value: string | null;
  date_format: string | null;
  validation_type: string | null;
  note: string | null;
}

export interface MappingReviewDetailRow {
  mapping_id: string;
  instrument_name: string;
  instrument_label: string;
  confidence: MappingConfidence;
  mapping_status: MappingStatus;
  notes: string[];
  selected_status_candidate: MappingFieldCandidate | null;
  selected_date_candidate: MappingFieldCandidate | null;
  status_options: MappingFieldOption[];
  date_options: MappingFieldOption[];
  selected_status_field_name: string;
  selected_date_field_name: string;
  selected_status_lock_value: string;
  selected_status_value_help: string | null;
  selected_date_format: string;
}

export interface MappingReviewDetail {
  job_id: string | null;
  job_status: string | null;
  total_rows: number;
  project_id: string | null;
  project_title: string | null;
  host_label: string | null;
  refresh_decision_pending: boolean;
  confirmed_mapping_count: number;
  mapping_none_option: string;
  mapping_auto_option: string;
  date_format_options: string[];
  rows: MappingReviewDetailRow[];
}

export interface ReportListItem {
  report_id: string;
  job_id: string;
  file_name: string;
  content_type: string;
  byte_size: number | null;
  checksum_sha256: string | null;
  job_status: JobStatus;
  project_id: string | null;
  project_title: string | null;
  request_file_name: string | null;
  host_label: string;
  updated_at: string;
}

export interface ReportsList {
  items: ReportListItem[];
}

export interface BackendActionResult {
  ok: boolean;
  message: string | null;
  redirect_path: string | null;
  redirect_query: Record<string, string>;
}

export interface UserRecord {
  id: string;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  is_two_factor_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}
