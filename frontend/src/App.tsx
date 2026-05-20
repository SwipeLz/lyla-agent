import { Outlet, Route, Routes } from "react-router-dom";
import { AppNavbar } from "./components/AppNavbar";
import { AuthGuard } from "./components/auth/AuthGuard";
import { PublicGuard } from "./components/auth/PublicGuard";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { TasksPage } from "./pages/TasksPage";
import { ExpensesPage } from "./pages/ExpensesPage";
import { LogsPage } from "./pages/LogsPage";
import { DevicesPage } from "./pages/DevicesPage";
import { ObservabilityPage } from "./pages/ObservabilityPage";
import { Link } from "react-router-dom";
import { BmoFace } from "./components/bmo/BmoFace";
import { BmoButton } from "./components/bmo/BmoButton";

function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-surface p-8 text-center">
      <BmoFace expression="dizzy" size={180} />
      <h1 className="text-2xl font-medium text-bmo-dark">
        Halaman tidak ditemukan
      </h1>
      <p className="max-w-md text-sm text-slate-600">
        URL yang kamu cari tidak ada. Periksa kembali atau kembali ke beranda.
      </p>
      <Link to="/">
        <BmoButton variant="primary">Kembali ke beranda</BmoButton>
      </Link>
    </div>
  );
}

function AppLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <AppNavbar />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/login"
        element={
          <PublicGuard>
            <LoginPage />
          </PublicGuard>
        }
      />
      <Route
        path="/app"
        element={
          <AuthGuard>
            <AppLayout />
          </AuthGuard>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="expenses" element={<ExpensesPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="devices" element={<DevicesPage />} />
        <Route path="observability" element={<ObservabilityPage />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
