// Reads a pasted materials sheet in the browser (nothing is uploaded). Each line is a property, a value and a unit,
// separated by tabs (pasted from a spreadsheet), commas or a colon. Lines it cannot use are reported, not guessed.
import type { Targets } from "@/lib/api";

type Field = keyof Targets;

const FIELDS: { field: Field; label: string; names: RegExp; units: RegExp }[] = [
  { field: "service_temp_c", label: "Min service temperature (°C)", names: /(service\s*)?temp(erature)?/i, units: /^(°?\s*c|deg\s*c|celsius)$/i },
  { field: "min_yield_strength_mpa", label: "Min yield (MPa)", names: /yield/i, units: /^mpa$/i },
  { field: "max_hafnium_at_pct", label: "Max hafnium (at%)", names: /hafnium|^\s*(max\s*)?hf\b/i, units: /^at\.?\s*%$/i },
];

export type SheetLine = { line: string; field?: Field; label?: string; value?: number; why?: string };
export type SheetResult = { targets: Partial<Targets>; read: SheetLine[]; skipped: SheetLine[] };

export function parseSheet(text: string): SheetResult {
  const result: SheetResult = { targets: {}, read: [], skipped: [] };
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const cells = line.split(/\t|,|:/).map((c) => c.trim()).filter(Boolean);
    const [name = "", valueCell = "", unitCell = ""] = cells;
    if (/^property$/i.test(name)) continue; // header row
    const f = FIELDS.find((x) => x.names.test(name));
    if (!f) {
      result.skipped.push({ line, why: "Not one of the three target properties" });
      continue;
    }
    const m = valueCell.match(/^(-?\d+(?:\.\d+)?)\s*(.*)$/);
    if (!m) {
      result.skipped.push({ line, why: "No number found" });
      continue;
    }
    const unit = (unitCell || m[2]).trim();
    if (unit && !f.units.test(unit)) {
      result.skipped.push({ line, why: `Unit "${unit}" is not ${f.label.match(/\((.*)\)/)?.[1]}` });
      continue;
    }
    const value = Number(m[1]);
    if (value < 0) {
      result.skipped.push({ line, why: "Negative value" });
      continue;
    }
    if (f.field in result.targets) {
      result.skipped.push({ line, why: `${f.label} was already read from an earlier line` });
      continue;
    }
    result.targets[f.field] = value;
    result.read.push({ line, field: f.field, label: f.label, value });
  }
  return result;
}

export const SAMPLE_SHEET = [
  "Property\tValue\tUnit",
  "Min service temperature\t1250\t°C",
  "Min yield\t650\tMPa",
  "Max hafnium\t0\tat%",
  "Density\t6.5\tg/cm3",
].join("\n");
