import { FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import * as api from "../lib/api";
import { ApiError } from "../lib/types";
import { BmoFace, BmoExpression } from "../components/bmo/BmoFace";
import { BmoButton } from "../components/bmo/BmoButton";
import { BmoInput } from "../components/bmo/BmoInput";

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success" }
  | { kind: "error"; message: string; rateLimited?: boolean };

const faceFor = (status: Status): BmoExpression => {
  switch (status.kind) {
    case "loading":
      return "excited";
    case "success":
      return "happy";
    case "error":
      return status.rateLimited ? "dizzy" : "sad";
    default:
      return "idle";
  }
};

const messageFor = (err: unknown): { message: string; rateLimited: boolean } => {
  if (err instanceof ApiError) {
    if (err.status === 429) {
      return {
        message:
          "Terlalu banyak percobaan login. Coba lagi dalam beberapa menit.",
        rateLimited: true,
      };
    }
    if (err.status === 401) {
      return { message: "Username atau password salah.", rateLimited: false };
    }
    return { message: err.message, rateLimited: false };
  }
  return { message: String(err), rateLimited: false };
};

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setStatus({
        kind: "error",
        message: "Isi username dan password dulu.",
      });
      return;
    }
    setStatus({ kind: "loading" });
    try {
      await api.login({ username: username.trim(), password });
      setStatus({ kind: "success" });
      navigate("/app", { replace: true });
    } catch (err) {
      const { message, rateLimited } = messageFor(err);
      setStatus({ kind: "error", message, rateLimited });
    }
  };

  if (status.kind === "success") {
    return <Navigate to="/app" replace />;
  }

  const disabled = status.kind === "loading";

  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <header className="px-4 py-4">
        <Link
          to="/"
          className="cursor-pointer text-sm text-slate-600 hover:text-bmo-dark"
        >
          ← Kembali ke beranda
        </Link>
      </header>
      <main className="flex flex-1 items-center justify-center px-4 pb-12">
        <div className="w-full max-w-md">
          <div className="rounded-lg border border-bmo-border bg-surface-elev p-6 shadow-sm">
            <div className="mb-4 flex flex-col items-center text-center">
              <BmoFace expression={faceFor(status)} size={140} />
              <h1 className="mt-3 text-xl font-medium text-bmo-dark">
                Masuk Dashboard
              </h1>
              <p className="mt-1 text-xs text-slate-500">
                Masukkan kredensial yang diberikan operator.
              </p>
            </div>
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label
                  htmlFor="username"
                  className="mb-1 block text-sm font-medium text-bmo-dark"
                >
                  Username
                </label>
                <BmoInput
                  id="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  disabled={disabled}
                />
              </div>
              <div>
                <label
                  htmlFor="password"
                  className="mb-1 block text-sm font-medium text-bmo-dark"
                >
                  Password
                </label>
                <BmoInput
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  disabled={disabled}
                />
              </div>
              {status.kind === "error" ? (
                <p
                  role="alert"
                  className="rounded border border-bmo-red/40 bg-pink-50 px-3 py-2 text-sm text-bmo-red"
                >
                  {status.message}
                </p>
              ) : null}
              <BmoButton
                type="submit"
                disabled={disabled}
                className="w-full"
              >
                {disabled ? "Memeriksa…" : "Masuk"}
              </BmoButton>
            </form>
            <p className="mt-4 text-center text-xs text-slate-500">
              Default operator: <code className="font-mono">admin</code> ·
              kontak admin untuk password.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
