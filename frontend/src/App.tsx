import { Link, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { SetupBanner } from "./components/SetupBanner";
import { DashboardPage } from "./pages/DashboardPage";
import { TasksPage } from "./pages/TasksPage";
import { ExpensesPage } from "./pages/ExpensesPage";
import { LogsPage } from "./pages/LogsPage";
import { DevicesPage } from "./pages/DevicesPage";
import { isReady } from "./lib/env";

function NotFound() {
  return (
    <section className="space-y-2">
      <h1 className="text-xl font-semibold">Halaman tidak ditemukan</h1>
      <p className="text-sm text-slate-600">
        Periksa kembali URL.{" "}
        <Link to="/" className="text-sky-700 underline">
          Kembali ke ringkasan
        </Link>
        .
      </p>
    </section>
  );
}

export function App() {
  const ready = isReady();
  if (!ready.ok) {
    return (
      <div className="min-h-screen bg-slate-50 p-8">
        <SetupBanner reason={ready.reason} />
      </div>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/expenses" element={<ExpensesPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/devices" element={<DevicesPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}
