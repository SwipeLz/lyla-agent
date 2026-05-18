import { useState } from "react";
import * as api from "../lib/api";
import { ApiError, AgentTextResponse } from "../lib/types";
import { DEMO_DEVICE_ID, DEMO_USER_ID } from "../lib/env";

interface AgentCommandBoxProps {
  onSuccess?: () => void;
}

const SAMPLE = "catat makan siang 20000";

export function AgentCommandBox({ onSuccess }: AgentCommandBoxProps) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AgentTextResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const reset = () => {
    setText("");
    setResult(null);
    setError(null);
  };

  const submit = async () => {
    if (!DEMO_USER_ID) return;
    const trimmed = text.trim();
    if (!trimmed) {
      setError(new ApiError("Perintah tidak boleh kosong.", 422));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await api.runAgentText({
        user_id: DEMO_USER_ID,
        device_id: DEMO_DEVICE_ID ?? undefined,
        text: trimmed,
        timezone: "Asia/Jakarta",
      });
      setResult(response);
      onSuccess?.();
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(String(err), 0));
    } finally {
      setLoading(false);
    }
  };

  const fb = result?.device_feedback as
    | { command?: { face?: string; sound?: string; text?: string } }
    | null
    | undefined;
  const command = fb?.command;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">Agent Command</h2>
        <span className="text-xs text-slate-500">
          Contoh: <code>{SAMPLE}</code>
        </span>
      </header>

      {!DEMO_DEVICE_ID ? (
        <p className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
          <code>VITE_DEMO_DEVICE_ID</code> belum diset. Perintah akan tetap
          dijalankan, tetapi <em>device feedback</em> tidak akan dikirim.
        </p>
      ) : null}

      <div className="mt-3">
        <textarea
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={SAMPLE}
          className="w-full rounded border border-slate-300 p-2 text-sm focus:border-slate-500 focus:outline-none"
          disabled={loading}
        />
      </div>

      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={loading || !DEMO_USER_ID}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {loading ? "Menjalankan…" : "Jalankan"}
        </button>
        <button
          type="button"
          onClick={reset}
          disabled={loading}
          className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Bersihkan
        </button>
      </div>

      {error ? (
        <div className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <div className="font-semibold">Gagal menjalankan perintah</div>
          <p className="mt-1 whitespace-pre-wrap">{error.message}</p>
        </div>
      ) : null}

      {result ? (
        <div className="mt-3 space-y-3">
          <div className="rounded border border-slate-200 bg-slate-50 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">
              Reply
            </div>
            <p className="mt-1 whitespace-pre-wrap text-sm text-slate-900">
              {result.reply}
            </p>
          </div>

          {fb ? (
            <div className="rounded border border-emerald-200 bg-emerald-50 p-3">
              <div className="text-xs uppercase tracking-wide text-emerald-700">
                Device Feedback
              </div>
              <dl className="mt-1 grid grid-cols-3 gap-2 text-sm">
                <div>
                  <dt className="text-xs text-emerald-700">Face</dt>
                  <dd className="font-medium text-emerald-900">
                    {command?.face ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-emerald-700">Sound</dt>
                  <dd className="font-medium text-emerald-900">
                    {command?.sound ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-emerald-700">Text</dt>
                  <dd className="font-medium text-emerald-900">
                    {command?.text ?? "—"}
                  </dd>
                </div>
              </dl>
            </div>
          ) : null}

          {result.actions.length > 0 ? (
            <details className="rounded border border-slate-200 bg-white p-3">
              <summary className="text-xs font-medium text-slate-600">
                {result.actions.length} aksi terdeteksi
              </summary>
              <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-700">
                {JSON.stringify(result.actions, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
