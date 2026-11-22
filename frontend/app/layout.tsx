import type { Metadata } from "next";
import localFont from "next/font/local";
import PasswordGate from "@/components/PasswordGate";
import PrototypeBanner from "@/components/app/PrototypeBanner";
import { THEME_KEY } from "@/lib/settings";
import { StoreProvider } from "@/lib/store";
import "./tokens.css"; // design tokens: the one place to change colors, fonts, spacing and radius
import "./globals.css";

export const metadata: Metadata = {
  title: "SDL Control Plane: scientist console",
  description: "Autonomous Lab Orchestration & Evidence Console",
};

// Inter, bundled in the repo (app/fonts, SIL Open Font License in Inter-OFL.txt), so the build never downloads it.
// One variable-font file for the Latin range covers the three weights used (400, 500, 600); every character the UI uses
// is in that range or falls back to the system font, as it did with the Google-hosted copy.
const inter = localFont({ src: "./fonts/Inter-latin.woff2", weight: "400 600", variable: "--font-inter", display: "swap" });

// The scientist console's theme: "light" or "dark" (colors in app/tokens.css). Light is the default, so a first visit
// opens in light; the header's theme switch saves the person's choice, and this script applies it before paint.
const DEFAULT_THEME = "light";
const APPLY_SAVED_THEME = `try{var t=localStorage.getItem("${THEME_KEY}");if(t==="dark"||t==="light")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme={DEFAULT_THEME} className={inter.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: APPLY_SAVED_THEME }} />
      </head>
      <body>
        <PrototypeBanner />
        <PasswordGate>
          <StoreProvider>{children}</StoreProvider>
        </PasswordGate>
      </body>
    </html>
  );
}
