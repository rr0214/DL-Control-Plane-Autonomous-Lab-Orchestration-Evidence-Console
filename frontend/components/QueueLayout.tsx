// Shared layout for list views (Customer queue, Internal experiments): one header, one Example data banner, one
// filter row and one card style, so the views look and behave the same. Colors come from the design tokens.

export type Tone = "ok" | "warn" | "danger" | "info" | "ai" | "cite" | "ink";

const CHIP_TONE: Record<Tone, string> = {
  ok: "bg-ok-100 text-ok-800 ring-ok-300",
  warn: "bg-warn-100 text-warn-900 ring-warn-300",
  danger: "bg-danger-100 text-danger-800 ring-danger-300",
  info: "bg-info-100 text-info-800 ring-info-300",
  ai: "bg-ai-100 text-ai-800 ring-ai-300",
  cite: "bg-cite-100 text-cite-800 ring-cite-300",
  ink: "bg-ink-200 text-ink-700 ring-ink-300",
};

export const PANEL_TONE: Record<Tone, string> = {
  ok: "bg-ok-50 text-ok-900 ring-ok-200",
  warn: "bg-warn-50 text-warn-900 ring-warn-200",
  danger: "bg-danger-50 text-danger-900 ring-danger-200",
  info: "bg-info-50 text-info-900 ring-info-200",
  ai: "bg-ai-50 text-ai-900 ring-ai-200",
  cite: "bg-cite-50 text-cite-900 ring-cite-200",
  ink: "bg-ink-50 text-ink-800 ring-ink-200",
};

export function StatusChip({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${CHIP_TONE[tone]}`}>
      {children}
    </span>
  );
}

export function ExampleDataBanner({ children }: { children: React.ReactNode }) {
  return (
    <div role="note" className="mb-4 rounded-lg bg-warn-50 px-3 py-2 text-sm text-warn-900 ring-1 ring-warn-200">
      <span className="font-semibold">Example data.</span> {children}
    </div>
  );
}

export type FilterOption<T extends string> = { id: T; label: string; count: number };

export function QueueView<T extends string>({
  title,
  description,
  banner,
  filters,
  filter,
  onFilter,
  children,
}: {
  title: string;
  description: string;
  banner: React.ReactNode;
  filters: FilterOption<T>[];
  filter: T;
  onFilter: (id: T) => void;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-3">
        <h2 className="text-lg font-semibold tracking-tight text-ink-900">{title}</h2>
        <p className="text-sm text-ink-600">{description}</p>
      </div>
      <ExampleDataBanner>{banner}</ExampleDataBanner>
      <div role="group" aria-label="Filter" className="mb-4 flex flex-wrap gap-2">
        {filters.map((f) => (
          <button
            key={f.id}
            onClick={() => onFilter(f.id)}
            aria-pressed={filter === f.id}
            className={`rounded-full px-3 py-1 text-sm font-medium ring-1 transition ${
              filter === f.id ? "bg-ink-900 text-surface ring-ink-900" : "bg-surface text-ink-700 ring-ink-300 hover:bg-ink-50"
            }`}
          >
            {f.label} <span className="opacity-70">{f.count}</span>
          </button>
        ))}
      </div>
      <ul className="space-y-3">{children}</ul>
    </section>
  );
}

export function QueueCard({
  dataId,
  title,
  subtitle,
  chip,
  children,
  footer,
}: {
  dataId: string;
  title: React.ReactNode;
  subtitle: React.ReactNode;
  chip: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <li data-id={dataId} className="rounded-xl bg-surface p-4 shadow-sm ring-1 ring-ink-200">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-ink-900">{title}</div>
          <div className="text-xs text-ink-500">{subtitle}</div>
        </div>
        {chip}
      </div>
      <div className="mt-3">{children}</div>
      {footer && <div className="mt-4 border-t border-ink-100 pt-3">{footer}</div>}
    </li>
  );
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-500">{children}</div>;
}

// Dates in the example data are fixed UTC times, shown the same way on every machine.
const DATE = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export const formatDate = (iso: string) => `${DATE.format(new Date(iso))} UTC`;
