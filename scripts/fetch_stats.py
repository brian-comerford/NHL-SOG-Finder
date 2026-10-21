"""Fetch the upcoming NHL slate, rosters, skater game logs and team
shots-against from the NHL's free public APIs (no key needed).

Writes:
  data/slate.json        the next game day's not-yet-started games
  data/players.json      every skater on a slate team's current roster,
                         with this season's and last season's game logs
  data/team_stats.json   shots for/against per game, this and last season
"""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

from common import (
    GAME_TYPES,
    NHL_STATS_API,
    NHL_WEB_API,
    TEAM_CODE_TO_NAME,
    get_json,
    normalize_name,
    previous_season_id,
    season_id_for,
    today_et,
    toi_to_minutes,
    utcnow_iso,
    write_json,
)

# The NHL API is free and unauthenticated; keep concurrency modest so a
# daily run never looks like abuse.
MAX_WORKERS = 6
UNSTARTED_STATES = {"FUT", "PRE"}


def team_full_name(team):
    place = (team.get("placeName") or {}).get("default", "")
    common = (team.get("commonName") or {}).get("default", "")
    return f"{place} {common}".strip()


def find_slate(start_date):
    """The first game day on or after `start_date` that still has games
    that haven't started. Only those unstarted games are included: once a
    game drops the puck, books pull its props and its picks are frozen
    (see analyze.snapshot_picks)."""
    payload = get_json(f"{NHL_WEB_API}/schedule/{start_date.isoformat()}") or {}
    for day in payload.get("gameWeek", []):
        games = [
            g
            for g in day.get("games", [])
            if g.get("gameType") in GAME_TYPES and g.get("gameState") in UNSTARTED_STATES
        ]
        if games:
            return day["date"], games
    return None, []


def slim_game(g):
    home, away = g["homeTeam"], g["awayTeam"]
    return {
        "game_id": g["id"],
        "season": g["season"],
        "game_type": g["gameType"],
        "start_time_utc": g.get("startTimeUTC"),
        "home_team": home["abbrev"],
        "away_team": away["abbrev"],
        "home_name": team_full_name(home) or TEAM_CODE_TO_NAME.get(home["abbrev"], home["abbrev"]),
        "away_name": team_full_name(away) or TEAM_CODE_TO_NAME.get(away["abbrev"], away["abbrev"]),
    }


def fetch_roster(team):
    payload = get_json(f"{NHL_WEB_API}/roster/{team}/current") or {}
    skaters = []
    for group in ("forwards", "defensemen"):
        for p in payload.get(group, []):
            first = (p.get("firstName") or {}).get("default", "")
            last = (p.get("lastName") or {}).get("default", "")
            skaters.append(
                {
                    "player_id": p["id"],
                    "player_name": f"{first} {last}".strip(),
                    "position": p.get("positionCode", "F"),
                    "team": team,
                    "sweater": p.get("sweaterNumber"),
                }
            )
    return skaters


def fetch_game_log(player_id, season):
    """Regular-season game log, most recent game first. Playoff games are
    left out of baselines: usage and pace change enough in the playoffs
    that mixing them in muddies a regular-season projection."""
    payload = get_json(f"{NHL_WEB_API}/player/{player_id}/game-log/{season}/2") or {}
    games = []
    for g in payload.get("gameLog", []):
        games.append(
            {
                "game_id": g.get("gameId"),
                "season": season,
                "date": g.get("gameDate"),
                "team": g.get("teamAbbrev"),
                "opponent": g.get("opponentAbbrev"),
                "home": g.get("homeRoadFlag") == "H",
                "shots": int(g.get("shots") or 0),
                "goals": int(g.get("goals") or 0),
                "toi": toi_to_minutes(g.get("toi")),
                "pp_points": int(g.get("powerPlayPoints") or 0),
            }
        )
    games.sort(key=lambda x: x["date"] or "", reverse=True)
    return games


def fetch_team_stats(season, name_to_code):
    url = f"{NHL_STATS_API}/team/summary"
    params = {"cayenneExp": f"seasonId={season} and gameTypeId=2"}
    payload = get_json(url, params=params) or {}
    out = {}
    for row in payload.get("data", []):
        code = name_to_code.get(normalize_name(row.get("teamFullName", "")))
        if not code or not row.get("gamesPlayed"):
            continue
        out[code] = {
            "games_played": row["gamesPlayed"],
            "shots_against_pg": row.get("shotsAgainstPerGame"),
            "shots_for_pg": row.get("shotsForPerGame"),
        }
    return out


def main():
    today = today_et()
    slate_date, games = find_slate(today)
    if not games:
        # Off-season / All-Star break: look a week further out before
        # giving up, so a short break doesn't blank the site.
        slate_date, games = find_slate(today + dt.timedelta(days=7))

    slate = [slim_game(g) for g in games]
    season = slate[0]["season"] if slate else season_id_for(today)
    prev_season = previous_season_id(season)
    print(f"Slate: {slate_date or 'none'} -- {len(slate)} unstarted games (season {season})")

    teams = sorted({g["home_team"] for g in slate} | {g["away_team"] for g in slate})
    with ThreadPoolExecutor(MAX_WORKERS) as pool:
        rosters = list(pool.map(fetch_roster, teams))
    skaters = [s for roster in rosters for s in roster]
    print(f"Rosters: {len(skaters)} skaters across {len(teams)} teams")

    def with_logs(skater):
        logs = fetch_game_log(skater["player_id"], season) + fetch_game_log(skater["player_id"], prev_season)
        return {**skater, "games": logs}

    with ThreadPoolExecutor(MAX_WORKERS) as pool:
        players = list(pool.map(with_logs, skaters))
    print(f"Game logs: {sum(len(p['games']) for p in players)} skater-games")

    name_to_code = {normalize_name(n): c for c, n in TEAM_CODE_TO_NAME.items()}
    for g in slate:
        name_to_code[normalize_name(g["home_name"])] = g["home_team"]
        name_to_code[normalize_name(g["away_name"])] = g["away_team"]
    team_stats = {
        "season": season,
        "current": fetch_team_stats(season, name_to_code),
        "previous": fetch_team_stats(prev_season, name_to_code),
    }
    print(
        f"Team stats: {len(team_stats['current'])} teams this season, "
        f"{len(team_stats['previous'])} last season"
    )

    write_json(
        "slate.json",
        {"slate_date": slate_date, "season": season, "fetched_at": utcnow_iso(), "games": slate},
    )
    write_json("players.json", players)
    write_json("team_stats.json", team_stats)


if __name__ == "__main__":
    main()
