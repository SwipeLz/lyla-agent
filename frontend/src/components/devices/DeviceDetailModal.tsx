import { useEffect, useRef, useState } from "react";
import * as api from "../../lib/api";
import {
  ApiError,
  AuthRequiredError,
  Device,
  DeviceDetailOut,
  DeviceStatusOut,
} from "../../lib/types";
import { BmoButton } from "../bmo/BmoButton";
import { BmoInput } from "../bmo/BmoInput";

type AnyDevice = Device | DeviceStatusOut;

interface DeviceDetailModalProps {
  open: boolean;
  device: AnyDevice | null;
  onClose: () => void;
  onChanged?: () => void;
  onDeleted?: () => void;
}

const parseUtcIso = (iso: string): number => {
  const hasTz = /Z|[+-]\d{2}:?\d{2}$/.test(iso);
  return new Date(hasTz ? iso : `${iso}Z`).getTime();
};

const formatTimeAgo = (iso: string | null | undefined): string => {
  if (!iso) return "belum pernah";
  const then = parseUtcIso(iso);
  if (Number.isNaN(then)) return iso;
  const diff = Date.now() - then;
  if (diff < 60_000) return "baru saja";
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} menit lalu`;
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} jam lalu`;
  return `${Math.floor(diff / 86400_000)} hari lalu`;
};

const maskToken = (token: string | null | undefined): string => {
  if (!token) return "—";
  const head = token.slice(0, 8);
  return `${head}••••••••`;
};

export function DeviceDetailModal({
  open,
  device,
  onClose,
  onChanged,
  onDeleted,
}: DeviceDetailModalProps) {
  const [detail, setDetail] = useState<DeviceDetailOut | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [tokenVisible, setTokenVisible] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<"save" | "delete" | "copy" | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open || !device) return;
    let cancelled = false;
    setDetail(null);
    setEditingName(false);
    setTokenVisible(false);
    setConfirmDelete(false);
    setError(null);
    setCopied(false);
    setLoading(true);
    void api
      .getDeviceDetail(device.id)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setNameDraft(d.name);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof AuthRequiredError) {
          setError("Sesi habis. Silakan login ulang.");
        } else if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError(String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, device]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (editingName) inputRef.current?.focus();
  }, [editingName]);

  if (!open || !device) return null;

  const handleSaveName = async () => {
    if (!detail) return;
    const trimmed = nameDraft.trim();
    if (!trimmed) {
      setError("Nama tidak boleh kosong.");
      return;
    }
    if (trimmed === detail.name) {
      setEditingName(false);
      return;
    }
    setBusy("save");
    setError(null);
    try {
      const updated = await api.updateDevice(detail.id, { name: trimmed });
      setDetail(updated);
      setEditingName(false);
      onChanged?.();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError(String(err));
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async () => {
    if (!detail) return;
    setBusy("delete");
    setError(null);
    try {
      await api.deleteDevice(detail.id);
      onDeleted?.();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError(String(err));
      setBusy(null);
    }
  };

  const handleCopyToken = async () => {
    if (!detail?.api_token) return;
    setBusy("copy");
    try {
      await navigator.clipboard.writeText(detail.api_token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Gagal menyalin ke clipboard.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="device-detail-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <button
        type="button"
        aria-label="Tutup modal"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
      />
      <div className="relative w-full max-w-lg rounded-lg border border-bmo-border bg-surface-elev shadow-lg">
        <div className="flex items-center justify-between border-b border-bmo-border px-5 py-3">
          <h2
            id="device-detail-title"
            className="text-base font-medium text-bmo-dark"
          >
            Detail Device
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Tutup"
            className="cursor-pointer rounded p-1 text-slate-500 hover:bg-bmo-screen/50 hover:text-bmo-dark"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          {loading ? (
            <p className="text-sm text-slate-500">Memuat detail…</p>
          ) : !detail ? (
            <p className="rounded border border-bmo-red/40 bg-pink-50 px-3 py-2 text-sm text-bmo-red">
              {error ?? "Detail tidak tersedia."}
            </p>
          ) : (
            <>
              <FieldRow label="Nama">
                {editingName ? (
                  <div className="flex flex-1 gap-2">
                    <BmoInput
                      ref={inputRef}
                      value={nameDraft}
                      onChange={(e) => setNameDraft(e.target.value)}
                      disabled={busy === "save"}
                    />
                    <BmoButton size="sm" onClick={handleSaveName} disabled={busy === "save"}>
                      {busy === "save" ? "…" : "Simpan"}
                    </BmoButton>
                    <BmoButton variant="secondary" size="sm" onClick={() => { setEditingName(false); setNameDraft(detail.name); }} disabled={busy === "save"}>
                      Batal
                    </BmoButton>
                  </div>
                ) : (
                  <div className="flex flex-1 items-center justify-between gap-2">
                    <span className="text-sm text-bmo-dark">{detail.name}</span>
                    <BmoButton variant="secondary" size="sm" onClick={() => setEditingName(true)}>
                      Edit
                    </BmoButton>
                  </div>
                )}
              </FieldRow>

              <FieldRow label="Device code">
                <code className="font-mono text-xs text-slate-700">{detail.device_code}</code>
              </FieldRow>

              <FieldRow label="Token">
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <code className="min-w-0 flex-1 break-all font-mono text-xs text-slate-700">
                    {tokenVisible ? detail.api_token ?? "—" : maskToken(detail.api_token)}
                  </code>
                  <div className="flex shrink-0 gap-1">
                    <BmoButton variant="secondary" size="sm" onClick={() => setTokenVisible((v) => !v)}>
                      {tokenVisible ? "Tutup" : "Lihat"}
                    </BmoButton>
                    <BmoButton variant="secondary" size="sm" onClick={handleCopyToken} disabled={!detail.api_token || busy === "copy"}>
                      {copied ? "Disalin ✓" : "Salin"}
                    </BmoButton>
                  </div>
                </div>
              </FieldRow>

              <FieldRow label="Status">
                <span className="text-sm text-bmo-dark">{detail.status}</span>
              </FieldRow>

              <FieldRow label="Last seen">
                <span className="text-sm text-bmo-dark">{formatTimeAgo(detail.last_seen_at)}</span>
              </FieldRow>

              <FieldRow label="Firmware">
                <span className="text-sm text-bmo-dark">{detail.firmware_version ?? "—"}</span>
              </FieldRow>

              <FieldRow label="RSSI / Battery">
                <span className="text-sm text-bmo-dark">
                  {detail.wifi_rssi_dbm != null ? `${detail.wifi_rssi_dbm} dBm` : "—"}
                  {" · "}
                  {detail.battery_pct != null && detail.battery_pct >= 0 ? `${detail.battery_pct}%` : "—"}
                </span>
              </FieldRow>

              {error ? (
                <p className="rounded border border-bmo-red/40 bg-pink-50 px-3 py-2 text-sm text-bmo-red">
                  {error}
                </p>
              ) : null}

              <div className="flex items-center justify-between border-t border-bmo-border pt-3">
                {!confirmDelete ? (
                  <BmoButton variant="secondary" size="sm" onClick={() => setConfirmDelete(true)}>
                    Hapus device
                  </BmoButton>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-600">Hapus permanen?</span>
                    <BmoButton size="sm" onClick={handleDelete} disabled={busy === "delete"}>
                      {busy === "delete" ? "Menghapus…" : "Ya, hapus"}
                    </BmoButton>
                    <BmoButton variant="secondary" size="sm" onClick={() => setConfirmDelete(false)} disabled={busy === "delete"}>
                      Batal
                    </BmoButton>
                  </div>
                )}
                <BmoButton variant="secondary" size="sm" onClick={onClose}>
                  Tutup
                </BmoButton>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </span>
      {children}
    </div>
  );
}
