import { formatDateTime } from "@/lib/format";
import { HistoryLine, STATUS_LABEL } from "@/lib/store";

// Every decision leaves a line: "Needs review to Accepted by R. Riggs", with the time.
export default function HistoryList({ lines }: { lines: HistoryLine[] }) {
  return (
    <section className="mt-5 border-t border-ink-200 pt-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-600">History</h3>
      <ol className="space-y-1 text-xs text-ink-700">
        {[...lines].reverse().map((l, i) => (
          <li key={i}>
            {l.from === null ? `New: ${STATUS_LABEL[l.to]}` : l.from === l.to ? STATUS_LABEL[l.to] : `${STATUS_LABEL[l.from]} to ${STATUS_LABEL[l.to]}`}{" "}
            by {l.by}
            {l.detail && ` (${l.detail})`} · {formatDateTime(l.at)}
          </li>
        ))}
      </ol>
    </section>
  );
}
