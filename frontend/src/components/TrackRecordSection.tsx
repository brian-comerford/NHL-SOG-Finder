import { useState } from "react";
import type { GradedPick, HitRateSummary, TrackRecord, TrackRecordDetail } from "../lib/types";
import { formatSlateDate, formatUnits } from "../lib/format";
import { pickUnits } from "../lib/odds";
import { fetchTrackRecordDetail } from "../lib/data";
import { useLockBodyScroll } from "../lib/useLockBodyScroll";

function pct(hitRate: number): string {
  return `${Math.round(hitRate * 100)}%`;
}

const RESULT_CLASS: Record<GradedPick["result"], string> = {
  win: "text-emerald-600 dark:text-emerald-400",
  loss: "text-red-500 dark:text-red-400",
  push: "text-slate-500 dark:text-slate-400",
};

// detail.picks arrives sorted most-recent-day-first; grouping keeps that.
function groupByDate(picks: GradedPick[]) {
  const groups: { date: string; picks: GradedPick[] }[] = [];
  for (const p of picks) {
    const last = groups[groups.length - 1];
    if (last && last.date === p.date) last.picks.push(p);
    else groups.push({ date: p.date, picks: [p] });
  }
  return groups;
}

export default function TrackRecordSection({ trackRecord }: { trackRecord: TrackRecord | null }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<TrackRecordDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!trackRecord?.overall) return null;
  const overall = trackRecord.overall;

  function handleOpen() {
    setOpen(true);
    if (!detail) {
      fetchTrackRecordDetail()
        .then(setDetail)
        .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    }
  }

  return (
    <div className="flex justify-center pb-4 pt-2">
      <button
        onClick={handleOpen}
        className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
      >
        Track record: {pct(overall.hit_rate)} ({overall.hits}/{overall.picks})
        {overall.priced_picks > 0 && <> &middot; {formatUnits(overall.units)}</>}
      </button>
      {open && <TrackRecordPanel trackRecord={trackRecord} detail={detail} error={error} onClose={() => setOpen(false)} />}
    </div>
  );
}

function TrackRecordPanel({
  trackRecord,
  detail,
  error,
  onClose,
}: {
  trackRecord: TrackRecord;
  detail: TrackRecordDetail | null;
  error: string | null;
  onClose: () => void;
}) {
  useLockBodyScroll();
  const rows: [string, HitRateSummary | undefined][] = [
    ["All picks", trackRecord.overall ?? undefined],
    ["High confidence", trackRecord.by_confidence.High],
    ["Medium confidence", trackRecord.by_confidence.Medium],
    ["Low confidence", trackRecord.by_confidence.Low],
    ["Overs", trackRecord.by_side.over],
    ["Unders", trackRecord.by_side.under],
  ];

  return (
    <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl dark:bg-slate-900 sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold">Track record</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Every positive-edge pick, graded against the final box score &middot; {trackRecord.days_graded} day
              {trackRecord.days_graded === 1 ? "" : "s"} graded
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {rows.map(([label, s]) =>
            s ? (
              <div key={label} className="rounded-lg bg-slate-100 p-2.5 dark:bg-slate-800">
                <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
                <div className="text-sm font-semibold">
                  {pct(s.hit_rate)} ({s.hits}/{s.picks})
                </div>
                <div className="text-xs text-slate-500 dark:text-slate-400">{formatUnits(s.units)}</div>
              </div>
            ) : null
          )}
        </div>

        {error && <p className="text-sm text-red-600">Couldn't load graded picks ({error}).</p>}
        {!error && !detail && <p className="text-sm text-slate-500">Loading picks…</p>}
        {detail &&
          groupByDate(detail.picks).map((group) => {
            const decided = group.picks.filter((p) => p.result !== "push");
            const wins = decided.filter((p) => p.result === "win").length;
            const units = decided
              .map((p) => pickUnits(p.price, p.result === "win"))
              .filter((u): u is number => u !== null);
            return (
              <details key={group.date} className="mb-2 rounded-lg border border-slate-200 dark:border-slate-800">
                <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
                  {formatSlateDate(group.date)} &middot; {wins}/{decided.length}
                  {units.length > 0 && <> &middot; {formatUnits(units.reduce((a, b) => a + b, 0))}</>}
                </summary>
                <ul className="divide-y divide-slate-100 border-t border-slate-200 text-sm dark:divide-slate-800 dark:border-slate-800">
                  {group.picks.map((p, i) => (
                    <li key={i} className="flex items-center justify-between gap-2 px-3 py-1.5">
                      <span>
                        {p.player_name}{" "}
                        <span className="text-xs text-slate-500 dark:text-slate-400">
                          {p.team} vs {p.opponent} &middot; {p.confidence}
                        </span>
                      </span>
                      <span className="whitespace-nowrap">
                        {p.side === "over" ? "O" : "U"} {p.line} &rarr; {p.actual}{" "}
                        <span className={`font-semibold uppercase ${RESULT_CLASS[p.result]}`}>{p.result}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            );
          })}
      </div>
    </div>
  );
}
