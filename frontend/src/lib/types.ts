export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export type DeviceFeedback = Record<string, unknown>;

export interface AgentTextRequest {
  user_id: string;
  device_id?: string;
  text: string;
  timezone?: string;
}

export interface AgentTextResponse {
  reply: string;
  actions: Array<Record<string, unknown>>;
  device_feedback: DeviceFeedback | null;
}

export interface DashboardSummary {
  tasks_due_today: number;
  total_expenses_today: number;
}

export interface Task {
  id: string;
  user_id: string;
  title: string;
  course: string | null;
  status: string;
  priority: string | null;
  deadline_at: string | null;
  reminder_at: string | null;
  created_at: string;
}

export type TaskPatchInput = Partial<
  Pick<
    Task,
    "status" | "title" | "course" | "deadline_at" | "reminder_at" | "priority"
  >
>;

export interface Expense {
  id: string;
  user_id: string;
  amount: number;
  category: string | null;
  note: string | null;
  spent_at: string;
  created_at: string;
}

export interface ExpenseCreateInput {
  user_id: string;
  amount: number;
  category?: string | null;
  note?: string | null;
  spent_at?: string | null;
}

export interface VoiceCommandLog {
  id: string;
  user_id: string | null;
  device_id: string | null;
  input_text: string;
  parsed_actions: Array<Record<string, unknown>> | null;
  response_text: string | null;
  status: string;
  created_at: string;
}

export interface Device {
  id: string;
  user_id: string;
  device_code: string;
  status: string;
  last_seen_at: string | null;
  created_at: string;
  firmware_version?: string | null;
  wifi_rssi_dbm?: number | null;
  battery_pct?: number | null;
  free_heap_bytes?: number | null;
}

export class AuthRequiredError extends Error {
  constructor(message = "Sesi tidak valid, silakan login ulang.") {
    super(message);
    this.name = "AuthRequiredError";
  }
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface MeResponse {
  username: string;
  expires_at: string;
}

export interface DevicePairRequest {
  name: string;
}

export interface DevicePairResponse {
  device_id: string;
  device_code: string;
  api_token: string;
  config_json: Record<string, unknown>;
}

export interface DeviceDetailOut {
  id: string;
  device_code: string;
  name: string;
  status: string;
  api_token: string | null;
  last_seen_at: string | null;
  firmware_version?: string | null;
  wifi_rssi_dbm?: number | null;
  battery_pct?: number | null;
  free_heap_bytes?: number | null;
  created_at?: string | null;
}

export interface DeviceUpdateRequest {
  name: string;
}

export interface StageTimings {
  validate?: number | null;
  stt?: number | null;
  agent?: number | null;
  classify?: number | null;
  tts?: number | null;
}

export interface TraceAudio {
  filename?: string | null;
  size_bytes?: number | null;
  content_type?: string | null;
}

export interface TraceTranscription {
  mode?: string | null;
  duration_ms?: number | null;
}

export interface TraceDirective {
  audio_code?: string | null;
  face?: string | null;
  screen_text?: string | null;
}

export interface TraceTts {
  mode?: string | null;
  available?: boolean | null;
  content_type?: string | null;
}

export interface TraceClient {
  request_id?: string | null;
  firmware_version?: string | null;
  wifi_rssi_dbm?: number | null;
  battery_pct?: number | null;
  recording_duration_ms?: number | null;
}

export interface TraceError {
  layer?: string | null;
  detail?: string | null;
}

export interface RequestTrace {
  id: string;
  user_id: string | null;
  device_id: string | null;
  input_text: string | null;
  response_text: string | null;
  parsed_actions: Array<Record<string, unknown>> | null;
  status: string;
  created_at: string;
  request_received_at: string | null;
  response_sent_at: string | null;
  stage_timings: StageTimings;
  audio: TraceAudio | null;
  audio_url: string | null;
  transcription: TraceTranscription | null;
  directive: TraceDirective | null;
  tts: TraceTts | null;
  client: TraceClient | null;
  error: TraceError | null;
}

export interface RecentLogSummary {
  id: string;
  device_id: string | null;
  created_at: string;
  audio_code: string | null;
  status: string;
  total_ms: number | null;
}

export interface TopAudioCode {
  code: string;
  count: number;
}

export interface StatsResponse {
  count: number;
  success_count: number;
  error_count: number;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  top_audio_codes: TopAudioCode[];
}

export interface DeviceStatusOut {
  id: string;
  device_code: string;
  name: string;
  status: string;
  is_online: boolean;
  last_seen_at: string | null;
  firmware_version: string | null;
  wifi_rssi_dbm: number | null;
  battery_pct: number | null;
  free_heap_bytes: number | null;
}
