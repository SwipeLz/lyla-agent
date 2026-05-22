import { useEffect, useState } from "react";
import * as api from "../../lib/api";
import {
  ApiError,
  AuthRequiredError,
  RequestTrace,
} from "../../lib/types";
import { BmoBadge } from "../bmo/BmoBadge";
import { BmoFace, BmoExpression } from "../bmo/BmoFace";
import { LoadingState } from "../LoadingState";
import { StageTimingBar } from "./StageTimingBar";

interface TraceDrawerProps {
  logId: string | null;
  onClose: () => void;
}

const faceFor = (trace: RequestTrace | null): BmoExpression => {
  if (!trace) return "idle";
  if (trace.status === "error") return "sad";
  const code = trace.directive?.audio_code ?? "";
  if (code === "fallback_tts") return "shock";
  if (code.startsWith("ok_")) return "happy";
  return "idle";
};

const fmtTime = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("id-ID", { hour12: false });
};

interface FieldProps {
  label: string;
  value: React.ReactNode;
}

function Field({ label, value }: FieldProps) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="mt-0.5 break-words text-sm text-bmo-dark">{value}</dd>
    </div>
  );
}

export function TraceDrawer({ logId, onClose }: TraceDrawerProps) {
  const [trace, setTrace] = useState<RequestTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!logId) {
      setTrace(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getTrace(logId)
      .then((data) => {
        if (!cancelled) setTrace(data);
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
  }, [logId]);

  useEffect(() => {
    if (!logId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [logId, onClose]);

  if (!logId) return null;

  return (
    <div className="fixed inset-0 z-40 flex">
      <button
        type="button"
        aria-label="Tutup detail"
        onClick={onClose}
        className="flex-1 cursor-default bg-black/30"
      />
      <aside
        role="dialog"
        aria-modal="true"
        className="flex w-full max-w-xl flex-col overflow-hidden bg-surface-elev shadow-xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-bmo-border bg-bmo-dark px-5 py-3 text-bmo-screen">
          <div className="flex items-center gap-3">
            <BmoFace expression={faceFor(trace)} size={56} />
            <div>
              <h2 className="text-base font-medium">Trace detail</h2>
              <p className="font-mono text-xs text-bmo-screen/70">{logId}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Tutup"
            className="cursor-pointer rounded p-1 hover:bg-bmo-mouth/30"
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

        <div className="flex-1 overflow-auto p-5">
          {loading ? <LoadingState label="Memuat trace…" /> : null}
          {error ? (
            <p className="rounded border border-bmo-red/40 bg-pink-50 px-3 py-2 text-sm text-bmo-red">
              {error}
            </p>
          ) : null}
          {trace ? (
            <div className="space-y-5">
              <section className="space-y-2">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-medium text-bmo-dark">
                    Status
                  </h3>
                  <BmoBadge
                    tone={trace.status === "error" ? "error" : "success"}
                  >
                    {trace.status}
                  </BmoBadge>
                </div>
                <dl className="grid grid-cols-2 gap-3">
                  <Field label="Created" value={fmtTime(trace.created_at)} />
                  <Field
                    label="Diterima"
                    value={fmtTime(trace.request_received_at)}
                  />
                  <Field
                    label="Dikirim"
                    value={fmtTime(trace.response_sent_at)}
                  />
                  <Field
                    label="Audio code"
                    value={trace.directive?.audio_code ?? "—"}
                  />
                </dl>
              </section>

              <section className="space-y-2">
                <h3 className="text-sm font-medium text-bmo-dark">
                  Stage timings
                </h3>
                <StageTimingBar timings={trace.stage_timings} />
              </section>

              {trace.error ? (
                <section className="space-y-1 rounded border border-bmo-red/40 bg-pink-50 p-3">
                  <h3 className="text-sm font-medium text-bmo-red">
                    Error layer: {trace.error.layer ?? "?"}
                  </h3>
                  <pre className="overflow-auto whitespace-pre-wrap font-mono text-xs text-bmo-red">
                    {trace.error.detail ?? "(tidak ada detail)"}
                  </pre>
                </section>
              ) : null}

              <section className="space-y-1">
                <h3 className="text-sm font-medium text-bmo-dark">
                  Transcript
                </h3>
                <p className="rounded border border-bmo-border bg-surface p-3 text-sm">
                  {trace.input_text ?? "—"}
                </p>
              </section>

              <section className="space-y-1">
                <h3 className="text-sm font-medium text-bmo-dark">Reply</h3>
                <p className="rounded border border-bmo-border bg-surface p-3 text-sm">
                  {trace.response_text ?? "—"}
                </p>
              </section>

              {trace.audio_url ? (
                <section className="space-y-2">
                  <h3 className="text-sm font-medium text-bmo-dark">
                    Audio input (debug)
                  </h3>
                  <audio
                    controls
                    src={trace.audio_url}
                    className="w-full"
                    preload="none"
                  >
                    Browser tidak mendukung pemutaran audio.
                  </audio>
                  <p className="text-xs text-slate-500">
                    File asli yang dikirim ESP32. Persistensi diaktifkan via{" "}
                    <code className="rounded bg-surface px-1">
                      AUDIO_PERSIST_INPUT_DIR
                    </code>
                    .
                  </p>
                </section>
              ) : null}

              {trace.client ? (
                <section className="space-y-2">
                  <h3 className="text-sm font-medium text-bmo-dark">
                    Telemetri client
                  </h3>
                  <dl className="grid grid-cols-2 gap-3">
                    <Field
                      label="Request ID"
                      value={trace.client.request_id ?? "—"}
                    />
                    <Field
                      label="Firmware"
                      value={trace.client.firmware_version ?? "—"}
                    />
                    <Field
                      label="RSSI"
                      value={
                        trace.client.wifi_rssi_dbm != null
                          ? `${trace.client.wifi_rssi_dbm} dBm`
                          : "—"
                      }
                    />
                    <Field
                      label="Battery"
                      value={
                        trace.client.battery_pct != null
                          ? `${trace.client.battery_pct}%`
                          : "—"
                      }
                    />
                    <Field
                      label="Recording"
                      value={
                        trace.client.recording_duration_ms != null
                          ? `${trace.client.recording_duration_ms} ms`
                          : "—"
                      }
                    />
                  </dl>
                </section>
              ) : null}

              {trace.parsed_actions && trace.parsed_actions.length > 0 ? (
                <section className="space-y-1">
                  <h3 className="text-sm font-medium text-bmo-dark">
                    Parsed actions
                  </h3>
                  <pre className="max-h-64 overflow-auto rounded border border-bmo-border bg-bmo-screen-dark p-3 font-mono text-xs text-bmo-screen">
                    {JSON.stringify(trace.parsed_actions, null, 2)}
                  </pre>
                </section>
              ) : null}
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
