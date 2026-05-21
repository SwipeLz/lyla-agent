import { API_BASE_URL } from "./env";
import {
  AgentTextRequest,
  AgentTextResponse,
  ApiError,
  AuthRequiredError,
  DashboardSummary,
  Device,
  DeviceDetailOut,
  DevicePairRequest,
  DevicePairResponse,
  DeviceStatusOut,
  DeviceUpdateRequest,
  Expense,
  ExpenseCreateInput,
  LoginRequest,
  MeResponse,
  RecentLogSummary,
  RequestTrace,
  StatsResponse,
  Task,
  TaskPatchInput,
  VoiceCommandLog,
} from "./types";

const NETWORK_DOWN = (base: string): string =>
  base
    ? `Backend tidak dapat dihubungi. Pastikan FastAPI berjalan di ${base}`
    : `Backend tidak dapat dihubungi. Pastikan FastAPI berjalan dan vite dev proxy aktif (cek frontend/vite.config.ts).`;

const buildHeaders = (
  extra: HeadersInit | undefined,
  hasJsonBody: boolean,
): HeadersInit => {
  const headers: Record<string, string> = {};
  if (hasJsonBody) {
    headers["Content-Type"] = "application/json";
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

const isAuthEndpoint = (path: string): boolean =>
  path.startsWith("/auth/");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  const hasJsonBody = typeof init?.body === "string";
  try {
    res = await fetch(API_BASE_URL + path, {
      ...init,
      credentials: "include",
      headers: buildHeaders(init?.headers, hasJsonBody),
    });
  } catch {
    throw new ApiError(NETWORK_DOWN(API_BASE_URL), 0);
  }

  if (res.status === 401 && !isAuthEndpoint(path)) {
    throw new AuthRequiredError();
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

export const login = (payload: LoginRequest): Promise<MeResponse> =>
  request<MeResponse>(`/auth/login`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const logout = (): Promise<void> =>
  request<void>(`/auth/logout`, { method: "POST" });

export const me = (): Promise<MeResponse> => request<MeResponse>(`/auth/me`);

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

export const pairDevice = (
  payload: DevicePairRequest,
): Promise<DevicePairResponse> =>
  request<DevicePairResponse>(`/devices/pair`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getDeviceDetail = (
  deviceId: string,
): Promise<DeviceDetailOut> =>
  request<DeviceDetailOut>(
    `/devices/id/${encodeURIComponent(deviceId)}`,
  );

export const updateDevice = (
  deviceId: string,
  payload: DeviceUpdateRequest,
): Promise<DeviceDetailOut> =>
  request<DeviceDetailOut>(
    `/devices/id/${encodeURIComponent(deviceId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );

export const deleteDevice = (deviceId: string): Promise<void> =>
  request<void>(`/devices/id/${encodeURIComponent(deviceId)}`, {
    method: "DELETE",
  });

export const getRecent = (params?: {
  limit?: number;
  device_id?: string;
  status?: string;
}): Promise<RecentLogSummary[]> =>
  request<RecentLogSummary[]>(
    `/observability/recent${qs({
      limit: params?.limit?.toString(),
      device_id: params?.device_id,
      status: params?.status,
    })}`,
  );

export const getTrace = (logId: string): Promise<RequestTrace> =>
  request<RequestTrace>(
    `/observability/trace/${encodeURIComponent(logId)}`,
  );

export const getStats = (
  window: "1h" | "24h" | "7d" = "1h",
): Promise<StatsResponse> =>
  request<StatsResponse>(`/observability/stats${qs({ window })}`);

export const getObsDevices = (): Promise<DeviceStatusOut[]> =>
  request<DeviceStatusOut[]>(`/observability/devices`);
