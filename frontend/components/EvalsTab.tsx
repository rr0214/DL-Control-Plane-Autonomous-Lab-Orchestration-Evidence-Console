// Golden dataset and judge metrics.
// The n=100 size and the override-rate endpoints come from the project plan.
// The 2x2 counts are illustrative placeholders and must be replaced with real eval output.

const GOLDEN_N = 100;
const MATRIX = { judgePassScientistPass: 46, judgePassScientistFail: 4, judgeFailScientistPass: 3, judgeFailScientistFail: 47 };
const OVERRIDE_RATE = [
  { label: "Week 1", value: 11.2 },
  { label: "Latest", value: 1.8 },
];

function Cell({ value, tone, label }: { value: number; tone: string; label: string }) {
  return (
    <div className={`flex flex-col items-center justify-center rounded-lg p-4 ${tone}`}>
      <span className="text-3xl font-semibold">{value}</span>
      <span className="mt-1 text-xs text-center">{label}</span>
    </div>
  );
}

export default function EvalsTab() {
  const total = MATRIX.judgePassScientistPass + MATRIX.judgePassScientistFail + MATRIX.judgeFailScientistPass + MATRIX.judgeFailScientistFail;
  const agreement = ((MATRIX.judgePassScientistPass + MATRIX.judgeFailScientistFail) / total) * 100;
  const maxRate = Math.max(...OVERRIDE_RATE.map((r) => r.value));

  return (
    <div className="space-y-4">
      <div className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900 ring-1 ring-amber-200">
        Demo values. The dataset size, override rates, and matrix counts are placeholders until the eval pipeline writes real results.
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Golden dataset</h2>
          <div className="mt-2 text-4xl font-semibold text-slate-900">n={GOLDEN_N}</div>
          <p className="mt-2 text-sm text-slate-600">
            Trace-derived. Each case is a real decision a scientist made at a Yellow gate, with its evidence attached.
          </p>
        </div>

        <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200 lg:col-span-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Judge vs scientist alignment (2x2)</h2>
          <div className="mt-3 grid grid-cols-[auto_1fr_1fr] gap-2 text-xs">
            <div />
            <div className="text-center font-medium text-slate-600">Scientist: pass</div>
            <div className="text-center font-medium text-slate-600">Scientist: fail</div>
            <div className="flex items-center font-medium text-slate-600">Judge: pass</div>
            <Cell value={MATRIX.judgePassScientistPass} tone="bg-emerald-100 text-emerald-900" label="Agree (pass)" />
            <Cell value={MATRIX.judgePassScientistFail} tone="bg-rose-100 text-rose-900" label="Judge too lenient" />
            <div className="flex items-center font-medium text-slate-600">Judge: fail</div>
            <Cell value={MATRIX.judgeFailScientistPass} tone="bg-rose-100 text-rose-900" label="Judge too strict" />
            <Cell value={MATRIX.judgeFailScientistFail} tone="bg-emerald-100 text-emerald-900" label="Agree (fail)" />
          </div>
          <p className="mt-3 text-sm text-slate-700">
            Agreement: <span className="font-semibold">{agreement.toFixed(0)}%</span> (illustrative)
          </p>
        </div>
      </div>

      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Scientist override rate</h2>
        <p className="mt-1 text-xs text-slate-500">Share of judge recommendations a scientist overrode, per week.</p>
        <div className="mt-4 space-y-3">
          {OVERRIDE_RATE.map((r) => (
            <div key={r.label}>
              <div className="flex justify-between text-xs text-slate-600">
                <span>{r.label}</span>
                <span className="font-semibold text-slate-900">{r.value.toFixed(1)}%</span>
              </div>
              <div className="mt-1 h-3 w-full rounded-full bg-slate-100">
                <div
                  className="h-3 rounded-full bg-slate-900"
                  style={{ width: `${(r.value / maxRate) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-sm text-slate-700">
          Scientist override rate fell from 11.2% to 1.8% between the first week and the latest week.
        </p>
      </div>
    </div>
  );
}
