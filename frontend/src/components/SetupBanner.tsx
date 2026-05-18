interface SetupBannerProps {
  reason: string;
}

export function SetupBanner({ reason }: SetupBannerProps) {
  return (
    <div className="mx-auto max-w-2xl rounded-lg border border-amber-300 bg-amber-50 p-6 text-sm text-amber-900 shadow-sm">
      <h2 className="text-base font-semibold">Setup belum lengkap</h2>
      <p className="mt-2">{reason}</p>
      <ol className="mt-4 list-decimal space-y-1 pl-5 text-amber-900/90">
        <li>
          Salin <code>frontend/.env.example</code> menjadi{" "}
          <code>frontend/.env</code>.
        </li>
        <li>
          Jalankan backend: <code>uvicorn app.main:app --reload</code>.
        </li>
        <li>
          Seed data demo: <code>python -m scripts.seed_dev</code> (catat UUID
          user dan device yang dicetak).
        </li>
        <li>
          Tempel <code>VITE_DEMO_USER_ID</code> dan
          <code> VITE_DEMO_DEVICE_ID</code> ke <code>frontend/.env</code>,
          lalu restart <code>npm run dev</code>.
        </li>
      </ol>
    </div>
  );
}
