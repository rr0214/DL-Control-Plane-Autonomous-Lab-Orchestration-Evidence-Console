import AppHeader from "@/components/app/AppHeader";
import ActiveExperiments from "@/components/experiments/ActiveExperiments";

// Active experiments: the lab's experiments (EXAMPLE) and the runs made here (LIVE), Active or Done.
export default function ActiveExperimentsPage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-5">
      <AppHeader />
      <ActiveExperiments />
    </main>
  );
}
