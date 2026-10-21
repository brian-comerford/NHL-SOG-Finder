import { Fragment, useMemo, useRef, useState } from "react";
import type { GridPosition, Matchups, Prop } from "../lib/types";
import {
  confidenceColorClass,
  edgeColorClass,
  formatBook,
  formatOdds,
  formatPct,
  formatPctWithOdds,
  formatStartTime,
} from "../lib/format";
import { sideBook, sideEdge, sideModelProb, sidePrice } from "../lib/odds";

interface Selection {
  defense: string;
  opponent: string;
  position: GridPosition;
}

const POSITION_NOUN: Record<GridPosition, string> = {
  LW: "left wings",
  C: "centers",
  RW: "right wings",
  D: "defensemen",
};

// Green = gives up the most shots at the position (a soft matchup for the
// shooters facing it), orange = gives up the fewest -- the same color
// convention as the classic "SOG given up by position" charts.
function rankClass(rank: number, teams: number): string {
  const pct = teams > 1 ? (rank - 1) / (teams - 1) : 0.5;
  if (pct >= 0.75) return "bg-emerald-200 text-emerald-950 dark:bg-emerald-800/70 dark:text-emerald-50";
  if (pct >= 0.6) return "bg-emerald-50 text-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-200";
  if (pct <= 0.25) return "bg-orange-200 text-orange-950 dark:bg-orange-800/60 dark:text-orange-50";
  if (pct <= 0.4) return "bg-orange-50 text-orange-900 dark:bg-orange-950/50 dark:text-orange-200";
  return "bg-white text-slate-800 dark:bg-slate-900 dark:text-slate-200";
}

function rankDescription(rank: number, teams: number): string {
  if (rank >= teams - 7) return "one of the most generous";
  if (rank <= 8) return "one of the stingiest";
  return "middle of the pack";
}

export default function MatchupGrid({
  matchups,
  props,
  onSelectProp,
}: {
  matchups: Matchups;
  props: Prop[];
  onSelectProp: (prop: Prop) => void;
}) {
  const teams = matchups.team_count || 32;
  const panelRef = useRef<HTMLDivElement>(null);

  // team -> position -> props for that team's skaters at that position
  const propsByTeamPos = useMemo(() => {
    const map = new Map<string, Prop[]>();
    for (const p of props) {
      const key = `${p.team}-${p.position}`;
      map.set(key, [...(map.get(key) ?? []), p]);
    }
    for (const list of map.values()) list.sort((a, b) => b.recommended_edge - a.recommended_edge);
    return map;
  }, [props]);

  // Open on the softest matchup on the slate, so the panel is never empty.
  const defaultSelection = useMemo<Selection | null>(() => {
    let best: (Selection & { rank: number }) | null = null;
    for (const g of matchups.games) {
      for (const [defense, opponent] of [
        [g.away_team, g.home_team],
        [g.home_team, g.away_team],
      ]) {
        for (const position of matchups.positions) {
          const rank = matchups.teams[defense]?.[position]?.rank;
          if (rank && propsByTeamPos.has(`${opponent}-${position}`) && (!best || rank > best.rank)) {
            best = { defense, opponent, position, rank };
          }
        }
      }
    }
    return best;
  }, [matchups, propsByTeamPos]);

  const [picked, setPicked] = useState<Selection | null>(null);
  const selection = picked ?? defaultSelection;

  function select(next: Selection) {
    setPicked(next);
    // On narrow screens the panel sits below the grid; bring it into view.
    if (window.matchMedia("(max-width: 1023px)").matches) {
      requestAnimationFrame(() => panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  }

  if (matchups.games.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center text-slate-500 dark:border-slate-700 dark:text-slate-400">
        No games on the upcoming slate.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] lg:items-start">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="border-b border-slate-200 px-3 py-2.5 dark:border-slate-800">
          <h2 className="text-sm font-semibold">SOG allowed by position</h2>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            Each row is a defense. 1 = fewest shots allowed at that position, {teams} = most. Tap a rank to see
            the opposing shooters.
          </p>
        </div>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-slate-100 text-slate-500 dark:bg-slate-800/60 dark:text-slate-400">
              <th className="px-2 py-1.5 text-left font-medium">Team</th>
              {matchups.positions.map((pos) => (
                <th key={pos} className="px-1 py-1.5 font-medium">
                  {pos === "D" ? "DEF" : pos}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matchups.games.map((g) => (
              <Fragment key={g.game_id}>
                {[
                  [g.away_team, g.home_team, true],
                  [g.home_team, g.away_team, false],
                ].map(([defense, opponent, first]) => (
                  <tr
                    key={defense as string}
                    className={first ? "border-t-2 border-slate-300 dark:border-slate-700" : "border-t border-slate-100 dark:border-slate-800"}
                  >
                    <td className="px-2 py-1">
                      <div className="font-semibold">{defense as string}</div>
                      <div className="text-[11px] leading-tight text-slate-500 dark:text-slate-400">
                        {first ? "@" : "vs"} {opponent as string}
                        {first && g.start_time_utc && <> &middot; {formatStartTime(g.start_time_utc)}</>}
                      </div>
                    </td>
                    {matchups.positions.map((pos) => {
                      const d = matchups.teams[defense as string]?.[pos];
                      const count = propsByTeamPos.get(`${opponent}-${pos}`)?.length ?? 0;
                      const isSelected =
                        selection?.defense === defense && selection?.position === pos;
                      if (!d) {
                        return (
                          <td key={pos} className="px-1 py-1 text-center text-slate-400">
                            —
                          </td>
                        );
                      }
                      return (
                        <td key={pos} className="p-0.5">
                          <button
                            onClick={() =>
                              select({ defense: defense as string, opponent: opponent as string, position: pos })
                            }
                            aria-pressed={isSelected}
                            aria-label={`${defense} rank ${d.rank} in shots allowed to ${POSITION_NOUN[pos]}`}
                            className={`flex w-full flex-col items-center rounded-md py-1 transition ${rankClass(d.rank, teams)} ${
                              isSelected
                                ? "ring-2 ring-slate-900 ring-offset-1 dark:ring-white dark:ring-offset-slate-900"
                                : "hover:brightness-95 dark:hover:brightness-125"
                            }`}
                          >
                            <span className="text-base font-bold leading-tight">{d.rank}</span>
                            <span className="text-[10px] leading-tight opacity-75">
                              {d.per_game.toFixed(1)}/g{count > 0 && <> &middot; {count}</>}
                            </span>
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-slate-200 px-3 py-2 text-[11px] text-slate-500 dark:border-slate-800 dark:text-slate-400">
          <span className="flex items-center gap-1">
            <span className="h-3 w-3 rounded-sm bg-emerald-200 dark:bg-emerald-800/70" /> Allows the most
          </span>
          <span className="flex items-center gap-1">
            <span className="h-3 w-3 rounded-sm bg-orange-200 dark:bg-orange-800/60" /> Allows the fewest
          </span>
          <span>Small text: SOG allowed per game &middot; props available</span>
        </div>
      </div>

      <div ref={panelRef} className="scroll-mt-4 lg:sticky lg:top-4">
        {selection ? (
          <MatchupPanel
            selection={selection}
            matchups={matchups}
            props={propsByTeamPos.get(`${selection.opponent}-${selection.position}`) ?? []}
            onSelectProp={onSelectProp}
          />
        ) : (
          <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
            Tap a ranking to see the opposing players at that position.
          </div>
        )}
      </div>
    </div>
  );
}

function MatchupPanel({
  selection,
  matchups,
  props,
  onSelectProp,
}: {
  selection: Selection;
  matchups: Matchups;
  props: Prop[];
  onSelectProp: (prop: Prop) => void;
}) {
  const { defense, opponent, position } = selection;
  const d = matchups.teams[defense][position];
  const teams = matchups.team_count || 32;
  const league = matchups.league_avg[position];
  const noun = POSITION_NOUN[position];

  return (
    <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="border-b border-slate-200 p-4 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <span
            className={`flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-lg ${rankClass(d.rank, teams)}`}
          >
            <span className="text-lg font-bold leading-none">{d.rank}</span>
            <span className="text-[9px] leading-none opacity-75">of {teams}</span>
          </span>
          <div>
            <h3 className="font-semibold">
              {opponent} {noun} vs. {defense}
            </h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {defense} is {rankDescription(d.rank, teams)} defenses against {noun}: {d.per_game.toFixed(2)} SOG/game
              allowed{league !== undefined && <> (league avg {league.toFixed(2)})</>} over {matchups.teams[defense].games}{" "}
              games. Model adjustment: {d.factor.toFixed(2)}x.
            </p>
          </div>
        </div>
      </div>

      {props.length === 0 ? (
        <p className="p-6 text-center text-sm text-slate-500 dark:text-slate-400">
          No shots-on-goal lines posted yet for {opponent} {noun}.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-100 text-left text-slate-500 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-400">
                <th className="px-3 py-2 font-medium">Player</th>
                <th className="px-3 py-2 font-medium">Line</th>
                <th className="px-3 py-2 font-medium">Pick</th>
                <th className="px-3 py-2 font-medium">Odds</th>
                <th className="px-3 py-2 font-medium">Model %</th>
                <th className="px-3 py-2 font-medium">Edge</th>
                <th className="px-3 py-2 font-medium">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {props.map((p) => {
                const side = p.recommended_side;
                const edge = sideEdge(p, side);
                return (
                  <tr
                    key={p.player_id}
                    onClick={() => onSelectProp(p)}
                    className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50 dark:border-slate-800/60 dark:hover:bg-slate-800/40"
                  >
                    <td className="px-3 py-2">
                      <div className="font-medium">{p.player_name}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">
                        Proj. {p.projected_sog.toFixed(2)} &middot; {p.avg_toi?.toFixed(1) ?? "—"} min TOI
                      </div>
                    </td>
                    <td className="px-3 py-2">{p.line}</td>
                    <td className="px-3 py-2 font-medium uppercase">{side}</td>
                    <td className="px-3 py-2">
                      {formatOdds(sidePrice(p, side))}
                      <div className="text-xs text-slate-500 dark:text-slate-400">{formatBook(sideBook(p, side))}</div>
                    </td>
                    <td className="px-3 py-2">{formatPctWithOdds(sideModelProb(p, side))}</td>
                    <td className={`px-3 py-2 ${edgeColorClass(edge ?? 0)}`}>{formatPct(edge)}</td>
                    <td className="px-3 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${confidenceColorClass(p.confidence)}`}>
                        {p.confidence}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="border-t border-slate-200 px-3 py-2 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
            Tap a player for the full breakdown and last-10-games chart. Edges already include this matchup.
          </p>
        </div>
      )}
    </div>
  );
}
