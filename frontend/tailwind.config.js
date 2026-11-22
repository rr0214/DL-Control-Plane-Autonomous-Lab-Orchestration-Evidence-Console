/** @type {import('tailwindcss').Config} */
// Tailwind names for the design tokens in app/tokens.css. Change values there, not here: this file only maps names
// (bg-ink-100, text-ok-700, font-mono, p-4, rounded-xl) to the CSS variables.
const defaultTheme = require("tailwindcss/defaultTheme");

const SHADES = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"];
const channel = (name) => `rgb(var(--${name}) / <alpha-value>)`;
const scale = (family) => Object.fromEntries(SHADES.map((s) => [s, channel(`${family}-${s}`)]));
const evidence = (kind) => ({ bg: channel(`evidence-${kind}-bg`), fg: channel(`evidence-${kind}-fg`), ring: channel(`evidence-${kind}-ring`) });

// Every step of Tailwind's spacing scale becomes a multiple of --space-unit (0.25rem by default, so p-4 is still 1rem).
const spacing = Object.fromEntries(
  Object.entries(defaultTheme.spacing).map(([key, value]) =>
    key === "px" || key === "0" ? [key, value] : [key, `calc(var(--space-unit) * ${parseFloat(value) / 0.25})`],
  ),
);

module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    spacing,
    extend: {
      colors: {
        surface: channel("surface"),
        page: channel("bg"),
        accent: channel("accent"),
        "on-accent": channel("on-accent"),
        warning: channel("warning"),
        ink: scale("ink"),
        ok: scale("ok"),
        warn: scale("warn"),
        danger: scale("danger"),
        error: scale("error"),
        info: scale("info"),
        ai: scale("ai"),
        cite: scale("cite"),
        evidence: {
          measured: evidence("measured"),
          predicted: evidence("predicted"),
          proposed: evidence("proposed"),
          literature: evidence("literature"),
        },
      },
      fontFamily: {
        sans: "var(--font-sans)",
        mono: "var(--font-mono)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        DEFAULT: "var(--radius)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        "2xl": "var(--radius-2xl)",
        "3xl": "var(--radius-3xl)",
      },
    },
  },
  plugins: [],
};
