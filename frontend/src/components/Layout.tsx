import { useState } from "react";
import { NavLink } from "react-router-dom";
import { DEMO_USER_ID, isReady } from "../lib/env";

const NAV_ITEMS: Array<{ to: string; label: string }> = [
  { to: "/", label: "Ringkasan" },
  { to: "/tasks", label: "Tugas" },
  { to: "/expenses", label: "Pengeluaran" },
  { to: "/logs", label: "Riwayat" },
  { to: "/devices", label: "Devices" },
];

const navLinkClass = ({ isActive }: { isActive: boolean }): string =>
  [
    "block rounded px-3 py-2 text-sm font-medium",
    isActive
      ? "bg-slate-900 text-white"
      : "text-slate-700 hover:bg-slate-200",
  ].join(" ");

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const [open, setOpen] = useState(false);
  const ready = isReady().ok;
  const truncatedUser = DEMO_USER_ID
    ? `${DEMO_USER_ID.slice(0, 8)}…`
    : "—";

  return (
    <div className="flex min-h-full flex-col md:flex-row">
      <aside className="border-b border-slate-200 bg-white md:w-60 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between p-4 md:flex-col md:items-stretch md:gap-4">
          <div>
            <h1 className="text-base font-semibold text-slate-900">
              Taskbot
            </h1>
            <p className="text-xs text-slate-500">Dashboard MVP</p>
          </div>
          <button
            type="button"
            className="rounded border border-slate-200 px-2 py-1 text-xs md:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls="primary-nav"
          >
            {open ? "Tutup" : "Menu"}
          </button>
          <nav
            id="primary-nav"
            className={[
              "space-y-1",
              open ? "block" : "hidden",
              "md:block",
            ].join(" ")}
          >
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={navLinkClass}
                onClick={() => setOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </aside>
      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-slate-200 bg-white px-6 py-3 text-sm">
          <div className="text-slate-600">
            User aktif:{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
              {truncatedUser}
            </code>
          </div>
          <span
            className={[
              "rounded-full px-2 py-0.5 text-xs font-medium",
              ready
                ? "bg-emerald-100 text-emerald-800"
                : "bg-red-100 text-red-800",
            ].join(" ")}
          >
            {ready ? "siap" : "belum siap"}
          </span>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
