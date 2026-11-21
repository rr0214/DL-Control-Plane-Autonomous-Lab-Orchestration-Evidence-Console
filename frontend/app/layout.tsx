import type { Metadata } from "next";
import { Inter } from "next/font/google";
import PasswordGate from "@/components/PasswordGate";
import "./tokens.css"; // design tokens: the one place to change colors, fonts, spacing and radius
import "./globals.css";

export const metadata: Metadata = {
  title: "SDL Control Plane",
  description: "Autonomous Lab Orchestration & Evidence Console",
};

// Inter, self-hosted by Next.js at build time (no request to Google from the browser). Only these three weights are used.
const inter = Inter({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-inter", display: "swap" });

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <PasswordGate>{children}</PasswordGate>
      </body>
    </html>
  );
}
