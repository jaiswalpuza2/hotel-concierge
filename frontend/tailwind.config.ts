import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#9F1D2B", dark: "#7C1621", soft: "#F8E7E9" },
        gold: { DEFAULT: "#C8962E", soft: "#FBF3E0" },
        ink: "#1F1A17",
        paper: "#FAF7F2",
      },
      fontFamily: {
        sans: [
          "Inter",
          "Noto Sans Devanagari",
          "Mukta",
          "ui-sans-serif",
          "system-ui",
          "Segoe UI",
          "sans-serif",
        ],
      },
      keyframes: {
        dot: { "0%, 80%, 100%": { opacity: "0.2" }, "40%": { opacity: "1" } },
      },
      animation: { dot: "dot 1.2s infinite ease-in-out" },
    },
  },
  plugins: [],
};

export default config;
