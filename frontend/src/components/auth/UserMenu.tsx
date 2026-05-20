import { useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../../lib/api";
import { useUser } from "./UserContext";

export function UserMenu() {
  const user = useUser();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await api.logout();
    } catch {
      // Even if logout API fails, clear UI state.
    }
    setOpen(false);
    setLoggingOut(false);
    navigate("/", { replace: true });
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-1.5 text-sm text-bmo-screen hover:bg-bmo-mouth/30 focus:outline-none focus:ring-2 focus:ring-bmo-body"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="font-medium">{user.username}</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open ? (
        <>
          <button
            type="button"
            aria-label="Tutup menu"
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div
            role="menu"
            className="absolute right-0 top-full z-20 mt-1 w-44 overflow-hidden rounded-md border border-bmo-border bg-surface-elev shadow-md"
          >
            <button
              type="button"
              onClick={handleLogout}
              disabled={loggingOut}
              role="menuitem"
              className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left text-sm text-bmo-dark hover:bg-bmo-screen disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loggingOut ? "Keluar…" : "Logout"}
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
