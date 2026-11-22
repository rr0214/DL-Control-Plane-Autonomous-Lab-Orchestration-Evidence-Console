import AppHeader from "@/components/app/AppHeader";
import ArchitectureTab from "@/components/ArchitectureTab";
import SystemDiagram, { SystemDiagramLegend } from "@/components/SystemDiagram";
import NodeMap from "@/components/architecture/NodeMap";
import TracesSection from "@/components/architecture/TracesSection";
import WhereAIFits from "@/components/architecture/WhereAIFits";

// For an interviewer: what this build is, what runs where, and what is real. Opens without the password.
export default function ArchitecturePage() {
  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-5">
      <AppHeader />
      <section className="rounded-lg bg-surface p-5 ring-1 ring-ink-200">
        <h2 className="text-lg font-semibold text-ink-900">How it works</h2>
        <p className="mt-2 max-w-3xl text-sm text-ink-800">
          This is a real working build of a prototype, not a mock. I built it as the product manager to understand the
          software pipeline of a self driving lab, where ML and AI fit inside it, and how it connects to the lab&apos;s
          guardrails. The scientist screens use example data, and the diagram below marks what is real and what is
          simulated. The AI steps call Claude through the Anthropic API, with mock replies as a fallback if no key is set.
        </p>
      </section>
      <section className="rounded-lg bg-surface p-5 ring-1 ring-ink-200">
        <h2 className="text-lg font-semibold text-ink-900">System architecture</h2>
        <p className="mt-1 text-sm text-ink-700">
          What runs where, how the parts talk, and what is real. Dashed, hatched boxes are simulated or example data.
        </p>
        <div className="mt-4">
          <SystemDiagram />
        </div>
        <SystemDiagramLegend />
      </section>
      <WhereAIFits />
      <NodeMap />
      <TracesSection />
      <ArchitectureTab />
    </main>
  );
}
