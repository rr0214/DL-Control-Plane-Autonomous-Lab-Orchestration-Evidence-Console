"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeSwitch from "./ThemeSwitch";
import { PHOENIX_TRACES_NOTE, PHOENIX_TRACES_URL, TRACES_SECTION } from "@/lib/settings";
import { useStore } from "@/lib/store";

// Header for every scientist screen: name, chips, Architecture link, theme switch, and the two tabs.
export default function AppHeader({ tabs = true }: { tabs?: boolean }) {
  const path = usePathname();
  const { needsReviewCount, activeCount } = useStore();
  const tab = path.startsWith("/experiments") ? "experiments" : path === "/" ? "review" : null;
  return (
    <header className="mb-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {/* Text wordmark. The real Radical logo is an open decision, so it is not used here. */}
          <span className="text-sm font-semibold uppercase tracking-[0.18em] text-ink-900">Radical</span>
          <span aria-hidden className="text-ink-300">/</span>
          <h1 className="text-lg font-semibold tracking-tight text-ink-900">SDL Control Plane</h1>
          <span className="rounded-full bg-ink-900 px-2 py-0.5 text-xs font-medium text-surface">Internal</span>
          <span className="rounded-full px-2 py-0.5 text-[11px] font-medium text-ink-700 ring-1 ring-ink-300">Example data</span>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/architecture" className="text-sm font-medium text-ink-700 underline-offset-2 hover:underline">
            Architecture
          </Link>
          {PHOENIX_TRACES_URL ? (
            <a
              href={PHOENIX_TRACES_URL}
              target="_blank"
              rel="noopener noreferrer"
              title={PHOENIX_TRACES_NOTE}
              className="text-sm font-medium text-ink-700 underline-offset-2 hover:underline"
            >
              Phoenix traces
              <span className="sr-only">
                {" "}
                (opens in a new tab). {PHOENIX_TRACES_NOTE}.
              </span>
            </a>
          ) : (
            <Link href={TRACES_SECTION} className="text-sm font-medium text-ink-700 underline-offset-2 hover:underline">
              Phoenix traces
            </Link>
          )}
          <ThemeSwitch />
        </div>
      </div>
      {tabs && (
        <nav aria-label="Sections" className="mt-4 flex gap-1 border-b border-ink-200">
          {[
            { id: "review", href: "/", label: "Review queue", count: needsReviewCount },
            { id: "experiments", href: "/experiments", label: "Active experiments", count: activeCount },
          ].map((t) => (
            <Link
              key={t.id}
              href={t.href}
              aria-current={tab === t.id ? "page" : undefined}
              className={`-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium ${
                tab === t.id ? "border-ink-900 text-ink-900" : "border-transparent text-ink-600 hover:text-ink-900"
              }`}
            >
              {t.label}
              <span className={`rounded-full px-1.5 text-xs ${tab === t.id ? "bg-accent text-on-accent" : "bg-ink-100 text-ink-700"}`}>
                {t.count}
              </span>
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
