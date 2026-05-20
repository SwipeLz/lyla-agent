/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bmo: {
          body: "#9FD5B1",
          screen: "#C5E3BF",
          mouth: "#1F8941",
          dark: "#1C4B3B",
          yellow: "#F7E72F",
          blue: "#313F98",
          "blue-light": "#C8CFFF",
          cyan: "#77CFDB",
          red: "#ED306A",
          purple: "#b297c7",
          "screen-dark": "#0D1B2A",
        },
        surface: {
          DEFAULT: "#F8FAF6",
          elev: "#FFFFFF",
        },
        "bmo-border": "#D1E0CC",
      },
      fontFamily: {
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      boxShadow: {
        bmo: "-2px 2px 0 2px #639975",
      },
    },
  },
  plugins: [],
};
