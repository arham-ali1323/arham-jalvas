import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#04070d",
        surface: "#0a111b",
        "surface-2": "#0f1724",
        border: "#16283a",
        muted: "#7f95ab",
        primary: {
          DEFAULT: "#22d3ee",
          soft: "#67e8f9",
          deep: "#0891b2",
        },
        accent: "#38bdf8",
        danger: "#f87171",
        success: "#34d399",
      },
      boxShadow: {
        glow: "0 0 24px rgba(34, 211, 238, 0.30)",
        "glow-sm": "0 0 12px rgba(34, 211, 238, 0.22)",
        panel: "0 20px 60px -20px rgba(0, 0, 0, 0.8)",
      },
      backgroundImage: {
        "grid-fade":
          "radial-gradient(circle at 50% -20%, rgba(34,211,238,0.15), transparent 55%)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.4s ease-out both",
        "pulse-glow": "pulseGlow 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
