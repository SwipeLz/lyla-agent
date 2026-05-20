export function PublicFooter() {
  return (
    <footer className="border-t border-bmo-border bg-surface-elev">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 text-sm text-slate-600 md:flex-row md:items-center md:justify-between">
        <p>
          Dibuat untuk skripsi · © {new Date().getFullYear()} Taskbot
        </p>
        <div className="flex gap-4">
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="cursor-pointer hover:text-bmo-dark"
          >
            GitHub
          </a>
          <a
            href="mailto:demo@taskbot.local"
            className="cursor-pointer hover:text-bmo-dark"
          >
            Email
          </a>
        </div>
      </div>
    </footer>
  );
}
