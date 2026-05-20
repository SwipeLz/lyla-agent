import { Link } from "react-router-dom";
import { PublicNavbar } from "../components/landing/PublicNavbar";
import { HeroSection } from "../components/landing/HeroSection";
import { FeatureCard } from "../components/landing/FeatureCard";
import { HowItWorksStep } from "../components/landing/HowItWorksStep";
import { FaqAccordion } from "../components/landing/FaqAccordion";
import { PublicFooter } from "../components/landing/PublicFooter";
import { BmoButton } from "../components/bmo/BmoButton";

const FEATURES = [
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M9 11l3 3L22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </svg>
    ),
    title: "Catat tugas",
    description:
      "Sebut nama tugas dan deadline-nya. Taskbot otomatis simpan dengan reminder yang tepat.",
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <line x1="12" y1="1" x2="12" y2="23" />
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
      </svg>
    ),
    title: "Pantau pengeluaran",
    description:
      "Catat makan siang, transport, atau jajan dengan suara. Lihat ringkasan harian dan bulanan.",
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
    ),
    title: "Reminder otomatis",
    description:
      "Atur pengingat lewat suara. BMO bakal nyala dan kasih notifikasi pas waktunya.",
  },
];

const STEPS = [
  {
    step: 1,
    expression: "idle" as const,
    title: "Tekan tombol",
    description: "BMO siap mendengarkan perintah suara.",
  },
  {
    step: 2,
    expression: "excited" as const,
    title: "Bicara",
    description: "Sebut tugas, pengeluaran, atau pengingat dalam bahasa sehari-hari.",
  },
  {
    step: 3,
    expression: "idle" as const,
    title: "Backend memproses",
    description: "Audio dikirim ke server, ditranskripsi dan dipahami AI.",
  },
  {
    step: 4,
    expression: "happy" as const,
    title: "BMO menjawab",
    description: "Konfirmasi balik lewat suara dan ekspresi muka.",
  },
];

const FAQ = [
  {
    q: "Apakah saya perlu hardware ESP32?",
    a: "Tidak wajib. Dashboard ini bisa dipakai mandiri lewat tombol 'Agent Command'. Hardware ESP32 menambah pengalaman push-to-talk fisik untuk demo.",
  },
  {
    q: "Apakah bisa offline?",
    a: "Backend butuh internet untuk Gemini API (transkripsi + agent). Mode fake tersedia untuk testing tanpa internet.",
  },
  {
    q: "Bahasa apa yang didukung?",
    a: "Bahasa Indonesia, fokus pada konteks pelajar. Sistem prompt + STT diset untuk Bahasa Indonesia.",
  },
  {
    q: "Berapa biayanya?",
    a: "Project skripsi, gratis. Cost utama dari Gemini API token usage di sisi backend operator.",
  },
];

export function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-surface text-bmo-dark">
      <PublicNavbar />
      <main className="flex-1">
        <HeroSection />

        <section
          id="fitur"
          className="mx-auto max-w-6xl px-4 py-16"
        >
          <div className="mb-8 text-center">
            <h2 className="text-2xl font-medium text-bmo-dark md:text-3xl">
              Tiga pilar Taskbot
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              Asisten kuliah ringkas yang fokus ke yang paling penting.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {FEATURES.map((f) => (
              <FeatureCard key={f.title} {...f} />
            ))}
          </div>
        </section>

        <section
          id="cara-kerja"
          className="bg-bmo-screen/30"
        >
          <div className="mx-auto max-w-6xl px-4 py-16">
            <div className="mb-8 text-center">
              <h2 className="text-2xl font-medium text-bmo-dark md:text-3xl">
                Cara kerja
              </h2>
              <p className="mt-2 text-sm text-slate-600">
                Empat langkah dari suara ke aksi tercatat.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-4">
              {STEPS.map((s) => (
                <HowItWorksStep key={s.step} {...s} />
              ))}
            </div>
          </div>
        </section>

        <section
          id="faq"
          className="mx-auto max-w-3xl px-4 py-16"
        >
          <div className="mb-6 text-center">
            <h2 className="text-2xl font-medium text-bmo-dark md:text-3xl">
              FAQ
            </h2>
          </div>
          <FaqAccordion items={FAQ} />
        </section>

        <section className="mx-auto max-w-3xl px-4 pb-16">
          <div className="rounded-lg border border-bmo-border bg-bmo-screen/40 p-8 text-center">
            <h2 className="text-xl font-medium text-bmo-dark">
              Siap mencoba?
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              Login dengan kredensial yang diberikan operator untuk mulai.
            </p>
            <div className="mt-4">
              <Link to="/login">
                <BmoButton variant="primary">Login sekarang</BmoButton>
              </Link>
            </div>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
