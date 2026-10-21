import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Prop } from "../lib/types";
import { formatBook, formatOdds, formatPct, formatPctWithOdds, formatShortDate, formatStartTime } from "../lib/format";
import { sideBook, sideEdge, sideImpliedProb, sideModelProb, sidePrice } from "../lib/odds";
import { useLockBodyScroll } from "../lib/useLockBodyScroll";

const BAR_UP = "#22c55e";
const BAR_DOWN = "#94a3b8";

export default function PropDetail({ prop, onClose }: { prop: Prop; onClose: () => void }) {
  useLockBodyScroll();
  const side = prop.recommended_side;
  const chartData = [...prop.recent_games].reverse().map((g) => ({
    label: `${formatShortDate(g.date)} ${g.home ? "vs" : "@"} ${g.opponent}`,
    value: g.shots,
    toi: g.toi,
  }));

  return (
    <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl dark:bg-slate-900 sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold">{prop.player_name}</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {prop.position} &middot; {prop.team} {prop.home ? "vs" : "@"} {prop.opponent} &middot; Shots on Goal
              {prop.start_time_utc && <> &middot; {formatStartTime(prop.start_time_utc)}</>}
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

        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Line" value={prop.line.toString()} />
          <Stat label="Projection" value={`${prop.projected_sog.toFixed(2)} SOG`} />
          <Stat label={`${side.toUpperCase()} odds`} value={formatOdds(sidePrice(prop, side))} />
          <Stat label="Source" value={formatBook(sideBook(prop, side))} />
          <Stat label="Edge" value={formatPct(sideEdge(prop, side))} highlight />
          <Stat label="Model probability" value={formatPctWithOdds(sideModelProb(prop, side))} />
          <Stat label="Book implied (no-vig)" value={formatPct(sideImpliedProb(prop, side))} />
          <Stat label="Confidence" value={prop.confidence} />
          <Stat
            label="This season"
            value={prop.season_avg_sog !== null ? `${prop.season_avg_sog.toFixed(2)} SOG (${prop.season_games}g)` : "—"}
          />
          <Stat label="Avg. ice time" value={prop.avg_toi !== null ? `${prop.avg_toi.toFixed(1)} min` : "—"} />
          <Stat label="Shots / 60" value={prop.shots_per_60 !== null ? prop.shots_per_60.toFixed(1) : "—"} />
          <Stat
            label={`${prop.opponent} vs ${prop.position}`}
            value={`${prop.opponent_factor.toFixed(2)}x${prop.opponent_pos_rank !== null ? ` (rank ${prop.opponent_pos_rank})` : ""}`}
          />
        </div>

        {prop.confidence_reasons.length > 0 && (
          <div className="mb-5 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
            <p className="mb-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">Why {prop.confidence} confidence</p>
            <ul className="space-y-1 text-sm">
              {prop.confidence_reasons.map((reason, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span
                    className={`mt-0.5 font-bold ${
                      reason.supports ? "text-emerald-600 dark:text-emerald-400" : "text-red-500 dark:text-red-400"
                    }`}
                    aria-label={reason.supports ? "supports the pick" : "against the pick"}
                  >
                    {reason.supports ? "+" : "−"}
                  </span>
                  <span>{reason.text}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {prop.trends.length > 0 && (
          <div className="mb-5 rounded-lg border border-emerald-200 bg-emerald-50 p-3 dark:border-emerald-900 dark:bg-emerald-950/30">
            <p className="mb-1.5 text-xs font-medium text-emerald-800 dark:text-emerald-300">Notable trends</p>
            <ul className="space-y-1 text-sm text-emerald-900 dark:text-emerald-200">
              {prop.trends.map((trend, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className="mt-0.5">&#8226;</span>
                  <span>{trend}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {chartData.length > 0 && (
          <div className="h-56 w-full">
            <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">Last {chartData.length} games vs. line</p>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={0} angle={-30} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8 }}
                  formatter={(value: number, _name, item) => {
                    const toi = (item.payload as { toi: number | null }).toi;
                    return [`${value}${toi ? ` (${toi.toFixed(1)} min TOI)` : ""}`, "Shots on goal"];
                  }}
                />
                <ReferenceLine
                  y={prop.line}
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  label={{ value: `Line ${prop.line}`, fontSize: 11, fill: "#f59e0b", position: "right" }}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {chartData.map((d, i) => (
                    <Cell key={i} fill={d.value > prop.line ? BAR_UP : BAR_DOWN} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="rounded-lg bg-slate-100 p-2.5 dark:bg-slate-800">
      <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
      <div className={`text-sm font-semibold ${highlight ? "text-emerald-600 dark:text-emerald-400" : ""}`}>{value}</div>
    </div>
  );
}
