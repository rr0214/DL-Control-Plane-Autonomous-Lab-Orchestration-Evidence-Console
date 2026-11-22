import Link from "next/link";
import { SHOW_PROTOTYPE_BANNER } from "@/lib/settings";

// Sits above everything on every screen. Hidden with SHOW_PROTOTYPE_BANNER in lib/settings.ts.
export default function PrototypeBanner() {
  if (!SHOW_PROTOTYPE_BANNER) return null;
  return (
    <div className="mx-auto max-w-7xl px-4 pt-4">
      <div role="note" className="flex rounded-lg border border-ink-200 bg-surface text-sm text-ink-800">
        <span aria-hidden className="w-1.5 shrink-0 rounded-l-lg bg-accent" />
        <p className="px-3 py-2">
          <span className="hidden sm:inline">
            Real working prototype, not a clickable demo. Claude runs the setup and diagnosis steps, plain code runs the
            safety checks, and a scientist approves. Example data.
          </span>
          <span className="sm:hidden">Real working prototype with Claude in the loop. Example data.</span>{" "}
          <Link href="/architecture" className="font-medium text-ink-900 underline underline-offset-2">
            See how it works
          </Link>
        </p>
      </div>
    </div>
  );
}
