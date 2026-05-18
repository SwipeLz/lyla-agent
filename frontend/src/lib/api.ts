import { API_BASE_URL, DASHBOARD_TOKEN } from "./env";
import {
  ApiError,
  AgentTextRequest,
  AgentTextResponse,
  DashboardSummary,
  Device,
  Expense,
  ExpenseCreateInput,
  Task,
  TaskPatchInput,
  VoiceCommandLog,
} from "./types";

const NETWORK_DOWN = (base: string): string =>
  base
    ? `Backend tidak dapat dihubungi. Pastikan FastAPI berjalan di ${base}`
    : `Backend tidak dapat dihubungi. Pastikan FastAPI berjalan dan vite dev proxy aktif (cek frontend/vite.config.ts).`;

const buildHeaders = (extra?: HeadersInit): HeadersInit => {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (DASHBOARD_TOKEN) {
    headers["X-Dashboard-Token"] = DASHBOARD_TOKEN;
  }
  if (extra) {
    const additional =
      extra instanceof Headers
        ? Object.fromEntries(extra.entries())
        : Array.isArray(extra)
          ? Object.fromEntries(extra)
          : (extra as Record<string, string>);
    Object.assign(headers, additional);
  }
  return headers;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE_URL + path, {
      ...init,
      headers: buildHeaders(init?.headers),
    });
  } catch {
    throw new ApiError(NETWORK_DOWN(API_BASE_URL), 0);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(detail || `HTTP ${res.status}`, res.status);
  }

  return (await res.json()) as T;
}

const qs = (params: Record<string, string | undefined | null>): string => {
  const out = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== "") out.set(k, v);
  }
  const s = out.toString();
  return s ? `?${s}` : "";
};

export const getSummary = (userId: string): Promise<DashboardSummary> =>
  request<DashboardSummary>(`/dashboard/summary${qs({ user_id: userId })}`);

export const getTasks = (userId: string, status?: string): Promise<Task[]> =>
  request<Task[]>(`/dashboard/tasks${qs({ user_id: userId, status })}`);

export const updateTask = (
  taskId: string,
  patch: TaskPatchInput,
): Promise<Task> =>
  request<Task>(`/dashboard/tasks/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

export const deleteTask = (taskId: string): Promise<void> =>
  request<void>(`/dashboard/tasks/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
  });

export const getExpenses = (userId: string): Promise<Expense[]> =>
  request<Expense[]>(`/dashboard/expenses${qs({ user_id: userId })}`);

export const createExpense = (
  input: ExpenseCreateInput,
): Promise<Expense> =>
  request<Expense>(`/dashboard/expenses`, {
    method: "POST",
    body: JSON.stringify(input),
  });

export const getLogs = (userId: string): Promise<VoiceCommandLog[]> =>
  request<VoiceCommandLog[]>(`/dashboard/logs${qs({ user_id: userId })}`);

export const getDevices = (userId: string): Promise<Device[]> =>
  request<Device[]>(`/dashboard/devices${qs({ user_id: userId })}`);

export const runAgentText = (
  payload: AgentTextRequest,
): Promise<AgentTextResponse> =>
  request<AgentTextResponse>(`/agent/text`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
