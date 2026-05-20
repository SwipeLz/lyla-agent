import { createContext, useContext } from "react";
import { MeResponse } from "../../lib/types";

export const UserContext = createContext<MeResponse | null>(null);

export function useUser(): MeResponse {
  const user = useContext(UserContext);
  if (!user) {
    throw new Error(
      "useUser harus dipakai di dalam <AuthGuard>. Pastikan halaman ada di route /app/*.",
    );
  }
  return user;
}
