import { ReactNode, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import * as api from "../../lib/api";
import { MeResponse } from "../../lib/types";
import { LoadingState } from "../LoadingState";
import { UserContext } from "./UserContext";

interface AuthGuardProps {
  children: ReactNode;
}

type AuthState =
  | { status: "loading" }
  | { status: "authenticated"; user: MeResponse }
  | { status: "unauthenticated" };

export function AuthGuard({ children }: AuthGuardProps) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((user) => {
        if (!cancelled) setState({ status: "authenticated", user });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "unauthenticated" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface p-8">
        <LoadingState label="Memeriksa sesi…" />
      </div>
    );
  }

  if (state.status === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }

  return (
    <UserContext.Provider value={state.user}>{children}</UserContext.Provider>
  );
}
