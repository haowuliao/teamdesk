/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#070b14", 900: "#0b1020", 850: "#0e1526", 800: "#11182c", 700: "#18223a", 600: "#1f2a44", 500: "#2b3a5c" },
        neon: { cyan: "#22d3ee", amber: "#fbbf24", green: "#34d399", red: "#f87171", violet: "#a78bfa" },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      animation: {
        "pulse-dot": "pulseDot 1.6s ease-in-out infinite",
        "blink": "blink 1s step-end infinite",
      },
      keyframes: {
        pulseDot: { "0%,100%": { opacity: "1", transform: "scale(1)" }, "50%": { opacity: "0.45", transform: "scale(1.35)" } },
        blink: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0" } },
      },
    },
  },
  plugins: [],
};
