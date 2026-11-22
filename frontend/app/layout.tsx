import type { Metadata } from "next";
import { Inter } from "next/font/google";
import PasswordGate from "@/components/PasswordGate";
import ThemePreview from "@/components/ThemePreview";
import PrototypeBanner from "@/components/app/PrototypeBanner";
import { THEME_KEY } from "@/components/app/ThemeSwitch";
import { StoreProvider } from "@/lib/store";
import "./tokens.css"; // design tokens: the one place to change colors, fonts, spacing and radius
import "./globals.css";

export const metadata: Metadata = {
  title: "SDL Control Plane: scientist console",
  description: "Autonomous Lab Orchestration & Evidence Console",
};

// Inter, self-hosted by Next.js at build time (no request to Google from the browser). Only these three weights are used.
const inter = Inter({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-inter", display: "swap" });

// The scientist console's theme: "light" or "dark" (colors in app/tokens.css). Light is the default; the header's
// theme switch saves the person's choice, and this script applies it before the first paint.
const DEFAULT_THEME = "light";
const APPLY_SAVED_THEME = `try{var t=localStorage.getItem("${THEME_KEY}");if(t==="dark"||t==="light")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme={DEFAULT_THEME} className={inter.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: APPLY_SAVED_THEME }} />
      </head>
      <body>
        <ThemePreview />
        <PrototypeBanner />
        <PasswordGate>
          <StoreProvider>{children}</StoreProvider>
        </PasswordGate>
      </body>
    </html>
  );
}
