import { Link } from "react-router-dom";
import { BmoMascot } from "../bmo/BmoMascot";
import { BmoButton } from "../bmo/BmoButton";

export function PublicNavbar() {
  return (
    <nav className="sticky top-0 z-30 bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link
          to="/"
          className="flex cursor-pointer items-center gap-2 text-bmo-dark"
        >
          <BmoMascot size={28} />
          <span className="text-base font-medium">Taskbot</span>
        </Link>
        <div className="hidden items-center gap-6 md:flex">
          <a
            href="#fitur"
            className="cursor-pointer text-sm text-slate-600 hover:text-bmo-dark"
          >
            Fitur
          </a>
          <a
            href="#cara-kerja"
            className="cursor-pointer text-sm text-slate-600 hover:text-bmo-dark"
          >
            Cara kerja
          </a>
          <a
            href="#faq"
            className="cursor-pointer text-sm text-slate-600 hover:text-bmo-dark"
          >
            FAQ
          </a>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/login">
            <BmoButton variant="secondary" size="sm">
              Login
            </BmoButton>
          </Link>
        </div>
      </div>
    </nav>
  );
}
