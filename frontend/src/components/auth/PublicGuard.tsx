import { ReactNode, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import * as api from "../../lib/api";
import { LoadingState } from "../LoadingState";

interface PublicGuardProps {
  children: ReactNode;
}

type AuthState = "loading" | "authenticated" | "unauthenticated";

export function PublicGuard({ children }: PublicGuardProps) {
  const [state, setState] = useState<AuthState>("loading");

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then(() => {
        if (!cancelled) setState("authenticated");
      })
      .catch(() => {
        if (!cancelled) setState("unauthenticated");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface p-8">
        <LoadingState label="Memeriksa sesi…" />
      </div>
    );
  }

  if (state === "authenticated") {
    return <Navigate to="/app" replace />;
  }

  return <>{children}</>;
}
