import { PHOENIX_TRACES_NOTE, PHOENIX_TRACES_URL } from "@/lib/settings";

// Where traces go, what is in them, where they are kept and who can read them. The header's "Phoenix traces" link
// lands here when no Phoenix project address is set. Every claim is checked against telemetry.py, graph.py, api.py,
// render.yaml and start.sh.
export default function TracesSection() {
  return (
    <section id="traces" className="scroll-mt-4 rounded-lg bg-surface p-5 ring-1 ring-ink-200">
      <h2 className="text-lg font-semibold text-ink-900">Traces</h2>
      <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-ink-800">
        <li>
          Every plan, review and release is traced with OpenTelemetry and sent to Arize Phoenix over OTLP/HTTP. Live runs go
          to the Phoenix project <span className="font-mono">sdl-control-plane</span>.
        </li>
        <li>
          A plan&apos;s trace has a span for each graph node, plus spans for the MCP tool calls, the Claude calls (with tokens,
          cost and latency), the safety gate, the scientist review, the measurement check, the action gate and the release
          sign-off.
        </li>
        <li>Tracing never blocks the app: if Phoenix cannot be reached when the API starts, the app runs without it.</li>
        <li>
          Phoenix keeps traces in its working directory, so they survive a restart: on Render a 1 GB disk on
          <span className="font-mono"> sdl-phoenix-rr</span>, locally <span className="font-mono">backend/data/phoenix</span>.
        </li>
        <li>
          Access: this build does not turn on a Phoenix login, so anyone with the Phoenix address can read the traces,
          including prompts and Claude&apos;s replies. Only example data is sent there.
        </li>
      </ul>
      <p className="mt-3 text-sm text-ink-800">
        {PHOENIX_TRACES_URL ? (
          <a
            href={PHOENIX_TRACES_URL}
            target="_blank"
            rel="noopener noreferrer"
            title={PHOENIX_TRACES_NOTE}
            className="font-medium text-ink-900 underline underline-offset-2"
          >
            Open the sdl-control-plane project in Phoenix ↗
          </a>
        ) : (
          "The Phoenix project address is not set for this console, so there is no direct link here."
        )}
      </p>
    </section>
  );
}
