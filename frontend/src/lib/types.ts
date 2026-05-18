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
}
