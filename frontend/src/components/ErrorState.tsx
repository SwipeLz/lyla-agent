import { ApiError } from "../lib/types";

interface ErrorStateProps {
  error: Error | ApiError;
  onRetry?: () => void;
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  const status = error instanceof ApiError ? error.status : null;
  const isNetwork = status === 0;

  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 shadow-sm"
    >
      <div className="font-semibold">
        {isNetwork ? "Backend tidak dapat dihubungi" : "Terjadi kesalahan"}
        {status != null && status > 0 ? (
          <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 text-xs font-normal text-red-700">
            HTTP {status}
          </span>
        ) : null}
      </div>
      <p className="mt-1 whitespace-pre-wrap">{error.message}</p>
      {isNetwork ? (
        <p className="mt-2 text-xs text-red-700">
          Pastikan FastAPI berjalan dan <code>VITE_API_BASE_URL</code> sesuai
          dengan port backend.
        </p>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
        >
          Coba lagi
        </button>
      ) : null}
    </div>
  );
}
