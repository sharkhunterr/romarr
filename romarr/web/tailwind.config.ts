import type { Config } from "tailwindcss";

// Spec 014 SCAF: Tailwind 3.x config. The shadcn/ui CSS variables
// (extending the colour palette via HSL custom props) land with the
// shadcn primitives slice — today we ship the bare Tailwind tokens
// plus the brand-default Game Boy LCD green (#9BBC0F) accent that
// the spec 013 Tag table references.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        brand: {
          // Game Boy LCD green — see spec 013 data-model on
          // tag.color default; also the operator UI accent.
          DEFAULT: "#9BBC0F",
          50: "#F4F8E0",
          100: "#E2EBA8",
          200: "#C5D770",
          300: "#A8C338",
          400: "#9BBC0F",
          500: "#7E9B0C",
          600: "#5F7409",
          700: "#3E4D06",
          800: "#1F2603",
          900: "#0D1001",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "Fira Code",
          "Menlo",
          "Monaco",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
