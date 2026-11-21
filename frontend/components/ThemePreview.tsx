"use client";

import { useEffect } from "react";

// PREVIEW ONLY, remove before merge: ?theme=dark or ?theme=light in the URL switches the theme so both can be
// compared in screenshots. To remove: delete this file and its two lines in app/layout.tsx (the import and
// <ThemePreview />), and the suppressHydrationWarning on <html>.
export default function ThemePreview() {
  useEffect(() => {
    const theme = new URLSearchParams(window.location.search).get("theme");
    if (theme === "dark" || theme === "light") document.documentElement.dataset.theme = theme;
  }, []);
  return null;
}
