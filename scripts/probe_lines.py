"""One-off probe: when do books post NHL shots-on-goal lines?

Run hourly by .github/workflows/probe-lines.yml. Each run checks every
not-yet-started game on today's ET slate and appends one row per game to
data/probe/lines_log.jsonl: how many players each book has a shots-on-goal
line for, and the newest `last_update` the API reports. Comparing rows
across hours shows when lines appear, which is what the daily refresh time
should be set around.

Uses ODDS_API_KEY_FREE (a separate free-tier key), so it never touches the
main key's quota. Cost: ~1 credit per game per run that has lines posted.
"""
import datetime as dt
import json
import os

import requests

from common import DATA_DIR, NHL_TZ

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "icehockey_nhl"
MARKET_KEY = "player_shots_on_goal"
BOOKMAKERS = "draftkings,fanduel"
LOG_PATH = os.path.join(DATA_DIR, "probe", "lines_log.jsonl")


def main():
    api_key = os.environ["ODDS_API_KEY_FREE"]
    now = dt.datetime.now(dt.timezone.utc)
    today_et = now.astimezone(NHL_TZ).date()

    # The events listing is free (0 credits).
    events = requests.get(f"{ODDS_API_BASE}/sports/{SPORT_KEY}/events", params={"apiKey": api_key}, timeout=30)
    events.raise_for_status()
    slate = []
    for e in events.json():
        start = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
        if start > now and start.astimezone(NHL_TZ).date() == today_et:
            slate.append((e, start))
    print(f"{now:%Y-%m-%d %H:%M} UTC: {len(slate)} unstarted games on the {today_et} slate")

    rows, remaining = [], None
    for e, start in slate:
        r = requests.get(
            f"{ODDS_API_BASE}/sports/{SPORT_KEY}/events/{e['id']}/odds",
            params={"apiKey": api_key, "bookmakers": BOOKMAKERS, "markets": MARKET_KEY, "oddsFormat": "american"},
            timeout=30,
        )
        remaining = r.headers.get("x-requests-remaining", remaining)
        if r.status_code != 200:
            print(f"  {e['away_team']} @ {e['home_team']}: HTTP {r.status_code} {r.text[:200]}")
            continue
        books = {}
        for bm in r.json().get("bookmakers", []):
            for market in bm.get("markets", []):
                if market.get("key") == MARKET_KEY:
                    players = {o.get("description") for o in market.get("outcomes", []) if o.get("description")}
                    books[bm["key"]] = {"players": len(players), "last_update": market.get("last_update")}
        row = {
            "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "checked_at_et": now.astimezone(NHL_TZ).strftime("%Y-%m-%d %I:%M %p"),
            "game": f"{e['away_team']} @ {e['home_team']}",
            "puck_drop_et": start.astimezone(NHL_TZ).strftime("%I:%M %p"),
            "books": books,
        }
        rows.append(row)
        summary = ", ".join(f"{k} {v['players']} players (updated {v['last_update']})" for k, v in books.items())
        print(f"  {row['game']} ({row['puck_drop_et']} ET): {summary or 'no lines yet'}")

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"Credits remaining on the free key: {remaining}")


if __name__ == "__main__":
    main()
