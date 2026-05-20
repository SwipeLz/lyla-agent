import { useEffect, useRef, useState } from "react";
import * as api from "../../lib/api";
import {
  ApiError,
  AuthRequiredError,
  DevicePairResponse,
} from "../../lib/types";
import { BmoButton } from "../bmo/BmoButton";
import { BmoInput } from "../bmo/BmoInput";

interface PairDeviceModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function PairDeviceModal({
  open,
  onClose,
  onSuccess,
}: PairDeviceModalProps) {
  const [name, setName] = useState("Lyla Demo Unit");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DevicePairResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setCopied(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    inputRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const handleSubmit = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Nama device tidak boleh kosong.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await api.pairDevice({ name: trimmed });
      setResult(response);
      onSuccess?.();
    } catch (err) {
      if (err instanceof AuthRequiredError) {
        setError("Sesi habis. Silakan login ulang.");
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(String(err));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(result.config_json, null, 2),
      );
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Gagal menyalin ke clipboard.");
    }
  };

  const handleClose = () => {
    setResult(null);
    setName("Lyla Demo Unit");
    setError(null);
    onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="pair-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <button
        type="button"
        aria-label="Tutup modal"
        className="absolute inset-0 cursor-default"
        onClick={handleClose}
      />
      <div className="relative w-full max-w-lg rounded-lg border border-bmo-border bg-surface-elev shadow-lg">
        <div className="flex items-center justify-between border-b border-bmo-border px-5 py-3">
          <h2
            id="pair-modal-title"
            className="text-base font-medium text-bmo-dark"
          >
            Pair Device Baru
          </h2>
          <button
            type="button"
            onClick={handleClose}
            aria-label="Tutup"
            className="cursor-pointer rounded p-1 text-slate-500 hover:bg-bmo-screen/50 hover:text-bmo-dark"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div className="space-y-4 px-5 py-4">
          {!result ? (
            <>
              <div>
                <label
                  htmlFor="device-name"
                  className="mb-1 block text-sm font-medium text-bmo-dark"
                >
                  Nama device
                </label>
                <BmoInput
                  ref={inputRef}
                  id="device-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Lyla Demo Unit"
                  disabled={loading}
                />
              </div>
              {error ? (
                <p className="rounded border border-bmo-red/40 bg-pink-50 px-3 py-2 text-sm text-bmo-red">
                  {error}
                </p>
              ) : null}
              <div className="flex justify-end gap-2 pt-2">
                <BmoButton
                  variant="secondary"
                  onClick={handleClose}
                  disabled={loading}
                >
                  Batal
                </BmoButton>
                <BmoButton onClick={handleSubmit} disabled={loading}>
                  {loading ? "Membuat…" : "Generate"}
                </BmoButton>
              </div>
            </>
          ) : (
            <>
              <p className="rounded border border-bmo-mouth/40 bg-bmo-screen/50 px-3 py-2 text-sm text-bmo-dark">
                ✓ Device berhasil dipair. Salin konfigurasi ke{" "}
                <code className="font-mono">/sd/config.json</code> lalu
                masukkan ke SD card ESP.
              </p>
              <pre className="max-h-72 overflow-auto rounded border border-bmo-border bg-bmo-screen-dark p-3 font-mono text-xs text-bmo-screen">
                {JSON.stringify(result.config_json, null, 2)}
              </pre>
              <div className="flex justify-end gap-2 pt-2">
                <BmoButton variant="secondary" onClick={handleCopy}>
                  {copied ? "Disalin ✓" : "Salin"}
                </BmoButton>
                <BmoButton onClick={handleClose}>Tutup</BmoButton>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
