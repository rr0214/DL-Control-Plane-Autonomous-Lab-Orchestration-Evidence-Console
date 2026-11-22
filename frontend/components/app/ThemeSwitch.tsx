"use client";

import { useEffect, useState } from "react";

// Dark is the default (matching the customer prototype). The choice is remembered in this browser (localStorage) and
// applied before the first paint by the small script in app/layout.tsx, so the page does not flash.
export const THEME_KEY = "sdl-theme";

export default function ThemeSwitch() {
  const [theme, setTheme] = useState<"light" | "dark" | null>(null);
  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  }, []);
  if (!theme) return <span className="inline-block h-8 w-16" aria-hidden />;
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      onClick={() => {
        document.documentElement.dataset.theme = next;
        try {
          window.localStorage.setItem(THEME_KEY, next);
        } catch {
          // storage blocked: the switch still works for this page
        }
        setTheme(next);
      }}
      aria-label={`Switch to ${next} theme`}
      className="rounded-lg px-2 py-1 text-xs font-medium text-ink-700 ring-1 ring-ink-500 hover:bg-ink-50"
    >
      {theme === "dark" ? "Light" : "Dark"} theme
    </button>
  );
}
