import { useState } from "react";
import { NavLink, Link } from "react-router-dom";
import { BmoMascot } from "./bmo/BmoMascot";
import { UserMenu } from "./auth/UserMenu";

const NAV_ITEMS: Array<{ to: string; label: string; end?: boolean }> = [
  { to: "/app", label: "Ringkasan", end: true },
  { to: "/app/tasks", label: "Tugas" },
  { to: "/app/expenses", label: "Pengeluaran" },
  { to: "/app/logs", label: "Riwayat" },
  { to: "/app/devices", label: "Devices" },
  { to: "/app/observability", label: "Observability" },
];

const linkClass = ({ isActive }: { isActive: boolean }): string =>
  [
    "cursor-pointer rounded px-2 py-1 text-sm transition-colors duration-200",
    isActive
      ? "text-bmo-screen border-b-2 border-bmo-body font-medium"
      : "text-bmo-screen/80 hover:text-bmo-screen",
  ].join(" ");

export function AppNavbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 bg-bmo-dark text-bmo-screen shadow-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
        <Link
          to="/app"
          className="flex shrink-0 cursor-pointer items-center gap-2"
        >
          <BmoMascot size={28} />
          <span className="text-base font-medium">Taskbot</span>
        </Link>
        <nav className="hidden flex-1 items-center justify-center gap-1 md:flex">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={linkClass}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="cursor-pointer rounded border border-bmo-screen/30 px-2 py-1 text-xs md:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls="mobile-nav"
          >
            {open ? "Tutup" : "Menu"}
          </button>
          <UserMenu />
        </div>
      </div>
      {open ? (
        <nav
          id="mobile-nav"
          className="border-t border-bmo-screen/20 bg-bmo-dark px-4 py-2 md:hidden"
        >
          <div className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={linkClass}
                onClick={() => setOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        </nav>
      ) : null}
    </header>
  );
}
