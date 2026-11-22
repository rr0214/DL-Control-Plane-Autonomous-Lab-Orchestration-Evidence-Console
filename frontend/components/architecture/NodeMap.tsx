import { GRAPH_NODES, LOOP_STEPS, STEPS_ON_NODES } from "@/lib/loopSteps";

// How the 10 console steps map onto the 7 LangGraph nodes in backend/app/graph.py. Built from lib/loopSteps.ts, so
// the page cannot claim more pipeline than the code has. Two steps run outside the graph and are listed separately.
export default function NodeMap() {
  const outside = LOOP_STEPS.filter((s) => s.nodes.length === 0);
  return (
    <section className="rounded-lg bg-surface p-5 ring-1 ring-ink-200">
      <h2 className="text-lg font-semibold text-ink-900">Console steps on the real graph</h2>
      <p className="mt-1 text-sm text-ink-700">
        {STEPS_ON_NODES} The nodes run in a fixed order; release and save-and-learn run outside the graph.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="text-left text-xs text-ink-600">
              <th className="py-1 pr-3 font-medium">#</th>
              <th className="py-1 pr-3 font-medium">Graph node</th>
              <th className="py-1 pr-3 font-medium">What it does</th>
              <th className="py-1 font-medium">Console steps that run on it</th>
            </tr>
          </thead>
          <tbody>
            {GRAPH_NODES.map((n, i) => (
              <tr key={n.id} className="border-t border-ink-200 align-top">
                <td className="py-1.5 pr-3 font-mono text-ink-600">{i + 1}</td>
                <td className="py-1.5 pr-3 font-mono text-ink-900">{n.id}</td>
                <td className="py-1.5 pr-3 text-ink-800">{n.what}</td>
                <td className="py-1.5 text-ink-900">
                  {LOOP_STEPS.filter((s) => s.nodes.includes(n.id))
                    .map((s) => `${s.name}${s.checkpoint ? " ★" : ""}`)
                    .join(", ")}
                </td>
              </tr>
            ))}
            {outside.map((s) => (
              <tr key={s.name} className="border-t border-ink-200 align-top">
                <td className="py-1.5 pr-3 text-ink-600">–</td>
                <td className="py-1.5 pr-3 text-ink-700">not a graph node</td>
                <td className="py-1.5 pr-3 text-ink-800">{s.outside}</td>
                <td className="py-1.5 text-ink-900">
                  {s.name}
                  {s.checkpoint ? " ★" : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
