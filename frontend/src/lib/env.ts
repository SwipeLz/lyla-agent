const trim = (value: string | undefined): string => (value ?? "").trim();

export const API_BASE_URL: string = trim(import.meta.env.VITE_API_BASE_URL);

export const DEMO_USER_ID: string | null =
  trim(import.meta.env.VITE_DEMO_USER_ID) || null;

export const DEMO_DEVICE_ID: string | null =
  trim(import.meta.env.VITE_DEMO_DEVICE_ID) || null;

export const DASHBOARD_TOKEN: string | null =
  trim(import.meta.env.VITE_DASHBOARD_TOKEN) || null;

export type ReadyStatus =
  | { ok: true; userId: string }
  | { ok: false; reason: string };

export const isReady = (): ReadyStatus => {
  if (!DEMO_USER_ID) {
    return {
      ok: false,
      reason:
        "VITE_DEMO_USER_ID belum diset. Salin .env.example menjadi .env, jalankan `python -m scripts.seed_dev`, lalu isi UUID demo user.",
    };
  }
  return { ok: true, userId: DEMO_USER_ID };
};
