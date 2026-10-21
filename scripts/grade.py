"""Grades past pick snapshots against final box scores and builds the
track record shown on the site.

For every data/history/picks_{date}.json, fetches each of that day's
games' box scores once the game is final and writes
data/history/results_{date}.json. A day is regraded on later runs until
every one of its games is final; after that it's left alone.

A pick on a skater who didn't dress (scratched, or a late injury) is
voided, the same way a sportsbook refunds it, rather than counted as a
loss.

Writes data/track_record.json (summary) and data/track_record_detail.json
(every graded pick).
"""
import glob
import os
import re

from common import HISTORY_DIR, NHL_WEB_API, get_json, load_json, pick_units, today_et, utcnow_iso, write_json

FINAL_STATES = {"OFF", "FINAL"}


def boxscore_shots(game_id):
    """(is_final, {player_id: shots}) for one game."""
    payload = get_json(f"{NHL_WEB_API}/gamecenter/{game_id}/boxscore") or {}
    if payload.get("gameState") not in FINAL_STATES:
        return False, {}
    shots = {}
    by_team = payload.get("playerByGameStats", {})
    for side in ("homeTeam", "awayTeam"):
        for group in ("forwards", "defense"):
            for p in by_team.get(side, {}).get(group, []):
                value = p.get("sog", p.get("shots"))
                if value is not None:
                    shots[p["playerId"]] = int(value)
    return True, shots


def grade_day(date, picks):
    graded, complete = [], True
    by_game = {}
    for pick in picks:
        by_game.setdefault(pick["game_id"], []).append(pick)
    for game_id, game_picks in by_game.items():
        final, shots = boxscore_shots(game_id)
        if not final:
            complete = False
            continue
        for pick in game_picks:
            actual = shots.get(pick["player_id"])
            if actual is None:
                graded.append({**pick, "date": date, "actual": None, "result": "void"})
                continue
            line = pick["line"]
            if actual == line:
                result = "push"
            elif (actual > line) == (pick["side"] == "over"):
                result = "win"
            else:
                result = "loss"
            graded.append({**pick, "date": date, "actual": actual, "result": result})
    return {"date": date, "complete": complete, "graded_at": utcnow_iso(), "picks": graded}


def grade_all():
    today = today_et().isoformat()
    for path in sorted(glob.glob(os.path.join(HISTORY_DIR, "picks_*.json"))):
        date = re.search(r"picks_(\d{4}-\d{2}-\d{2})\.json$", path)
        if not date or date.group(1) > today:
            continue
        date = date.group(1)
        existing = load_json(f"history/results_{date}.json")
        if existing and existing.get("complete"):
            continue
        picks = (load_json(f"history/picks_{date}.json") or {}).get("picks", [])
        result = grade_day(date, picks)
        write_json(f"history/results_{date}.json", result)
        print(f"Graded {date}: {len(result['picks'])} picks ({'complete' if result['complete'] else 'partial'})")


def summarize(picks):
    decided = [p for p in picks if p["result"] in ("win", "loss")]
    if not decided:
        return None
    wins = sum(p["result"] == "win" for p in decided)
    units = [pick_units(p.get("price"), p["result"] == "win") for p in decided]
    priced = [u for u in units if u is not None]
    return {
        "picks": len(decided),
        "hits": wins,
        "hit_rate": round(wins / len(decided), 4),
        "units": round(sum(priced), 2) if priced else None,
        "priced_picks": len(priced),
        "pushes": sum(p["result"] == "push" for p in picks),
    }


def build_track_record():
    all_picks, days = [], 0
    for path in sorted(glob.glob(os.path.join(HISTORY_DIR, "results_*.json"))):
        day = load_json(os.path.relpath(path, os.path.dirname(HISTORY_DIR))) or {}
        if day.get("picks"):
            days += 1
        all_picks.extend(day.get("picks", []))

    write_json(
        "track_record.json",
        {
            "overall": summarize(all_picks),
            "by_confidence": {
                c: s for c in ("Low", "Medium", "High") if (s := summarize([p for p in all_picks if p["confidence"] == c]))
            },
            "by_side": {
                side: s for side in ("over", "under") if (s := summarize([p for p in all_picks if p["side"] == side]))
            },
            "days_graded": days,
            "updated_at": utcnow_iso(),
        },
    )
    detail = [
        {
            "date": p["date"],
            "player_name": p["player_name"],
            "position": p["position"],
            "team": p["team"],
            "opponent": p["opponent"],
            "line": p["line"],
            "side": p["side"],
            "confidence": p["confidence"],
            "edge": p["edge"],
            "price": p.get("price"),
            "actual": p["actual"],
            "result": p["result"],
        }
        for p in all_picks
        if p["result"] != "void"
    ]
    detail.sort(key=lambda p: (p["date"], p["edge"]), reverse=True)
    write_json("track_record_detail.json", {"updated_at": utcnow_iso(), "picks": detail})
    print(f"Track record: {len(detail)} graded picks over {days} days")


def main():
    grade_all()
    build_track_record()


if __name__ == "__main__":
    main()
