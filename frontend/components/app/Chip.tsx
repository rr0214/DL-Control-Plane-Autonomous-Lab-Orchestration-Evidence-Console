export type Tone = "ok" | "warn" | "danger" | "info" | "ai" | "cite" | "ink";

const TONE: Record<Tone, string> = {
  ok: "bg-ok-100 text-ok-800 ring-ok-300",
  warn: "bg-warn-100 text-warn-900 ring-warn-300",
  danger: "bg-danger-100 text-danger-800 ring-danger-300",
  info: "bg-info-100 text-info-800 ring-info-300",
  ai: "bg-ai-100 text-ai-800 ring-ai-300",
  cite: "bg-cite-100 text-cite-800 ring-cite-300",
  ink: "bg-ink-100 text-ink-800 ring-ink-300",
};

export default function Chip({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${TONE[tone]}`}>
      {children}
    </span>
  );
}
