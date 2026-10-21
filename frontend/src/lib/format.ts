import { probToAmericanOdds } from "./odds";

const BOOK_LABELS: Record<string, string> = {
  draftkings: "DraftKings",
  fanduel: "FanDuel",
  sample: "Sample",
};

export function formatBook(book: string | null): string {
  if (!book) return "—";
  return BOOK_LABELS[book] ?? book;
}

export function formatOdds(odds: number | null): string {
  if (odds === null || Number.isNaN(odds)) return "—";
  return odds > 0 ? `+${odds}` : `${odds}`;
}

export function formatPct(value: number | null, digits = 1): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

// Same as formatPct, plus the American odds that probability implies, e.g.
// "50.0% (-100)" -- for comparing directly against the book's price.
export function formatPctWithOdds(value: number | null, digits = 1): string {
  if (value === null || Number.isNaN(value)) return "—";
  const odds = probToAmericanOdds(value);
  const suffix = odds === null ? "" : ` (${formatOdds(odds)})`;
  return `${(value * 100).toFixed(digits)}%${suffix}`;
}

export function formatUnits(units: number | null): string {
  if (units === null) return "—";
  const sign = units > 0 ? "+" : units < 0 ? "-" : "";
  return `${sign}${Math.abs(units).toFixed(2)}u`;
}

// Puck drop in the viewer's own time zone, e.g. "7:00 PM".
export function formatStartTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// "2026-10-21" -> "Wed, Oct 21", parsed as a calendar date (not UTC
// midnight, which would show the previous day west of Greenwich).
export function formatSlateDate(date: string | null): string {
  if (!date) return "";
  const [y, m, d] = date.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

export function formatShortDate(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], { month: "numeric", day: "numeric" });
}

export function edgeColorClass(edge: number): string {
  if (edge >= 0.06) return "text-emerald-600 dark:text-emerald-400 font-semibold";
  if (edge > 0) return "text-emerald-700/80 dark:text-emerald-400/80";
  return "text-slate-500 dark:text-slate-400";
}

export function confidenceColorClass(confidence: string): string {
  switch (confidence) {
    case "High":
      return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300";
    case "Medium":
      return "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300";
    default:
      return "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300";
  }
}

export function pillClass(selected: boolean): string {
  return `rounded-full border px-2 py-0.5 text-xs transition-colors ${
    selected
      ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
      : "border-slate-300 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
  }`;
}
