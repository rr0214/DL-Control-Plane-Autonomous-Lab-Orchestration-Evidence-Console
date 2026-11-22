import { Suspense } from "react";
import AppHeader from "@/components/app/AppHeader";
import AddExperiment from "@/components/addexp/AddExperiment";

// Add experiment: set targets, plan a batch on the real backend, review it, and see the results.
export default function AddExperimentPage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-5">
      <AppHeader />
      {/* AddExperiment reads ?from= and ?followup= from the URL, which Next.js needs inside a Suspense boundary. */}
      <div className="max-w-5xl">
        <Suspense fallback={<p className="text-sm text-ink-700">Loading...</p>}>
          <AddExperiment />
        </Suspense>
      </div>
    </main>
  );
}
