// Says where an item comes from, so nothing example is presented as real.
// LIVE: read from or written to the running backend. EXAMPLE: fictional data that lives only in this browser.
export default function SourceTag({ kind }: { kind: "live" | "example" }) {
  const live = kind === "live";
  return (
    <span
      title={live ? "From the running backend" : "Example data: fictional, kept only in this browser"}
      className={`inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide ring-1 ${
        live ? "bg-ok-100 text-ok-800 ring-ok-300" : "bg-ink-100 text-ink-700 ring-ink-300"
      }`}
    >
      {live ? "Live" : "Example"}
    </span>
  );
}
