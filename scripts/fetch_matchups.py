"""Shots on goal allowed by position: for every team, how many shots
opposing left wings, centers, right wings and defensemen put on it per
game, ranked 1 (fewest allowed) to 32 (most allowed).

Built from final box scores. Box scores never change once a game is
final, so each game's per-position tallies are cached in
data/cache/position_shots.json (committed back by CI, like pick history)
and only new games are fetched on later runs. The first run backfills
this season and last season (~1,400 box scores, a few minutes).

Writes data/position_defense.json, which analyze.py uses both for the
matchup grid and as the opponent adjustment in the projection.
"""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

from common import (
    NHL_WEB_API,
    get_json,
    load_json,
    previous_season_id,
    season_id_for,
    today_et,
    utcnow_iso,
    write_json,
)

CACHE = "cache/position_shots.json"
POSITIONS = ["LW", "C", "RW", "D"]
BOX_POSITION = {"L": "LW", "C": "C", "R": "RW", "D": "D"}
FINAL_STATES = {"OFF", "FINAL"}
MAX_WORKERS = 6
# A team's this-season rate is shrunk toward its own last-season rate (or
# the league average) with this many games' worth of weight, so ten
# October games don't produce a ranking that's mostly noise.
SHRINK_GAMES = 10
FACTOR_BOUNDS = (0.8, 1.2)


def completed_games(start, end, seasons):
    """(game_id, season, date) for every final regular-season game between
    `start` and `end`, scanning the weekly schedule endpoint."""
    games, day = {}, start
    while day <= end:
        payload = get_json(f"{NHL_WEB_API}/schedule/{day.isoformat()}") or {}
        for week_day in payload.get("gameWeek", []):
            for g in week_day.get("games", []):
                if g.get("gameType") == 2 and g.get("season") in seasons and g.get("gameState") in FINAL_STATES:
                    games[g["id"]] = (g["season"], week_day["date"])
        day += dt.timedelta(days=7)
    return games


def position_tallies(game_id):
    """{team: {pos: shots by that team's skaters}} for one final game.
    Shots *allowed* by a team are the other side's tallies."""
    payload = get_json(f"{NHL_WEB_API}/gamecenter/{game_id}/boxscore") or {}
    if payload.get("gameState") not in FINAL_STATES:
        return None
    teams = {
        "homeTeam": (payload.get("homeTeam") or {}).get("abbrev"),
        "awayTeam": (payload.get("awayTeam") or {}).get("abbrev"),
    }
    stats = payload.get("playerByGameStats", {})
    shots_by = {}
    for side, team in teams.items():
        tally = {p: 0 for p in POSITIONS}
        for group in ("forwards", "defense"):
            for p in stats.get(side, {}).get(group, []):
                pos = BOX_POSITION.get(p.get("position")) or ("D" if group == "defense" else None)
                if pos:
                    tally[pos] += int(p.get("sog", p.get("shots")) or 0)
        shots_by[team] = tally
    if None in shots_by or len(shots_by) != 2:
        return None
    home, away = teams["homeTeam"], teams["awayTeam"]
    return {"home": home, "away": away, "against": {home: shots_by[away], away: shots_by[home]}}


def update_cache(season):
    prev = previous_season_id(season)
    cache = load_json(CACHE, {}) or {}
    games = cache.get("games", {})
    today = today_et()
    if cache.get("scanned_through"):
        start = dt.date.fromisoformat(cache["scanned_through"]) - dt.timedelta(days=7)
    else:
        start = dt.date(int(str(prev)[:4]), 9, 25)
    found = completed_games(start, today, {season, prev})
    missing = [gid for gid in found if str(gid) not in games]
    print(f"Position cache: {len(games)} games cached, {len(missing)} new to fetch")

    with ThreadPoolExecutor(MAX_WORKERS) as pool:
        for gid, tallies in zip(missing, pool.map(position_tallies, missing)):
            if tallies:
                season_id, date = found[gid]
                games[str(gid)] = {"season": season_id, "date": date, **tallies}

    # Only keep the two seasons in use so the committed cache doesn't grow
    # forever.
    games = {k: v for k, v in games.items() if v["season"] in (season, prev)}
    write_json(CACHE, {"scanned_through": today.isoformat(), "updated_at": utcnow_iso(), "games": games})
    return games


def per_game_rates(games, season):
    """team -> pos -> (shots allowed per game, games)."""
    totals = {}
    for g in games.values():
        if g["season"] != season:
            continue
        for team, tally in g["against"].items():
            t = totals.setdefault(team, {"games": 0, **{p: 0 for p in POSITIONS}})
            t["games"] += 1
            for p in POSITIONS:
                t[p] += tally.get(p, 0)
    return {
        team: {p: (t[p] / t["games"], t["games"]) for p in POSITIONS}
        for team, t in totals.items()
        if t["games"]
    }


def build(games, season):
    current = per_game_rates(games, season)
    previous = per_game_rates(games, previous_season_id(season))

    def league_avg(rates, pos):
        vals = [r[pos][0] for r in rates.values()]
        return sum(vals) / len(vals) if vals else None

    teams = {}
    league = {}
    for pos in POSITIONS:
        lg_prev = league_avg(previous, pos)
        lg_cur = league_avg(current, pos) or lg_prev
        if lg_cur is None:
            continue
        league[pos] = round(lg_cur, 3)
        shrunk = {}
        for team in set(current) | set(previous):
            prior = previous.get(team, {}).get(pos, (lg_prev or lg_cur, 0))[0]
            rate, gp = current.get(team, {}).get(pos, (prior, 0))
            shrunk[team] = (gp * rate + SHRINK_GAMES * prior) / (gp + SHRINK_GAMES)
            lg = (gp * lg_cur + SHRINK_GAMES * (lg_prev or lg_cur)) / (gp + SHRINK_GAMES)
            lo, hi = FACTOR_BOUNDS
            teams.setdefault(team, {"games": gp})[pos] = {
                "per_game": round(rate, 2),
                "adjusted": round(shrunk[team], 2),
                "factor": round(min(max(shrunk[team] / lg, lo), hi), 3),
            }
        # 1 = fewest shots allowed at this position, 32 = most -- the same
        # convention as the classic "SOG given up by position" charts.
        for rank, team in enumerate(sorted(shrunk, key=shrunk.get), start=1):
            teams[team][pos]["rank"] = rank
    return {"season": season, "positions": POSITIONS, "league_avg": league, "team_count": len(teams), "teams": teams}


def main(season=None):
    season = season or (load_json("slate.json", {}) or {}).get("season") or season_id_for(today_et())
    games = update_cache(season)
    result = build(games, season)
    write_json("position_defense.json", {**result, "updated_at": utcnow_iso()})
    print(f"Position defense: ranked {result['team_count']} teams")


if __name__ == "__main__":
    main()
