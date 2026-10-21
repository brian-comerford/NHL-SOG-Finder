"""Fetch player shots-on-goal odds for the upcoming slate.

Live mode: calls The Odds API (https://the-odds-api.com), free tier 500
credits/month. Requires an ODDS_API_KEY environment variable / GitHub
Actions secret.

Sample mode (automatic fallback): with no key, or if the live call fails
or returns nothing, this builds clearly-labeled sample odds from each
skater's own recent shot average with a randomized line and vig, so the
site works out of the box. `odds_meta.json` records which mode ran and
the frontend surfaces it.

Output (data/odds_quotes.json) is a flat list of quotes:
{
  player_name, game_id, point,
  price_over, price_under,     # American odds
  book_over, book_under        # e.g. "draftkings" / "fanduel" / "sample"
}
"""
import os
import random
import time
from collections import Counter

import requests

from common import TEAM_CODE_TO_NAME, load_json, normalize_name, utcnow_iso, write_json

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "icehockey_nhl"
MARKET_KEY = "player_shots_on_goal"
# Both books are in The Odds API's "us" region, so each event costs one
# credit per market -- a full ~16-game night is ~17 credits, comfortably
# inside the free tier at one run a day.
BOOKMAKERS = "draftkings,fanduel"

# Books rarely post shot props for depth players, so the sample feed
# skips anyone averaging less than this.
SAMPLE_MIN_AVG_SHOTS = 1.2
SAMPLE_MIN_GAMES = 5


def slate_lookup(slate):
    """normalized frozenset(home name, away name) -> game_id, keyed on both
    the NHL's own spelling and the sportsbook spelling of each team."""
    lookup = {}
    for g in slate:
        homes = {normalize_name(g["home_name"]), normalize_name(TEAM_CODE_TO_NAME.get(g["home_team"], ""))}
        aways = {normalize_name(g["away_name"]), normalize_name(TEAM_CODE_TO_NAME.get(g["away_team"], ""))}
        for h in homes:
            for a in aways:
                lookup[frozenset((h, a))] = g["game_id"]
    return lookup


def fetch_live(slate, api_key):
    resp = requests.get(f"{ODDS_API_BASE}/sports/{SPORT_KEY}/events", params={"apiKey": api_key}, timeout=30)
    resp.raise_for_status()
    events = resp.json()

    # Match the exact matchup -- books post future days' games too, and
    # those would burn credits on games that aren't on this slate.
    lookup = slate_lookup(slate)
    relevant = []
    for e in events:
        key = frozenset((normalize_name(e["home_team"]), normalize_name(e["away_team"])))
        if key in lookup:
            relevant.append((e, lookup[key]))
    print(f"Found {len(relevant)} slate events out of {len(events)} listed")

    quotes = []
    for event, game_id in relevant:
        url = f"{ODDS_API_BASE}/sports/{SPORT_KEY}/events/{event['id']}/odds"
        params = {
            "apiKey": api_key,
            "bookmakers": BOOKMAKERS,
            "markets": MARKET_KEY,
            "oddsFormat": "american",
        }
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            print(f"  skipping event {event['id']} ({status})")
            if status == 401:
                print(
                    "  401 usually means the monthly quota is used up or the key is invalid "
                    "-- check https://the-odds-api.com/account/. Stopping further calls."
                )
                break
            continue
        except requests.RequestException as exc:
            print(f"  skipping event {event['id']} ({exc})")
            continue
        quotes.extend(parse_event_odds(r.json(), game_id))
        time.sleep(0.25)
    return quotes


def parse_event_odds(payload, game_id):
    """One quote per player: the most common (median) line across books,
    with the most bettor-favorable over and under price at that line."""
    # player -> side -> [(point, price, book)]
    buckets = {}
    for bm in payload.get("bookmakers", []):
        for market in bm.get("markets", []):
            if market.get("key") != MARKET_KEY:
                continue
            for outcome in market.get("outcomes", []):
                player = outcome.get("description")
                side = outcome.get("name", "").lower()
                if not player or side not in ("over", "under"):
                    continue
                buckets.setdefault(player, {}).setdefault(side, []).append(
                    (outcome.get("point"), outcome.get("price"), bm.get("key"))
                )

    quotes = []
    for player, sides in buckets.items():
        over, under = sides.get("over", []), sides.get("under", [])
        points = sorted(p for p, _, _ in over + under if p is not None)
        if not over or not under or not points:
            continue
        point = points[len(points) // 2]
        over_at = [(pr, bk) for pt, pr, bk in over if pt == point]
        under_at = [(pr, bk) for pt, pr, bk in under if pt == point]
        if not over_at or not under_at:
            continue
        price_over, book_over = max(over_at, key=lambda x: x[0])
        price_under, book_under = max(under_at, key=lambda x: x[0])
        quotes.append(
            {
                "player_name": player,
                "game_id": game_id,
                "point": point,
                "price_over": price_over,
                "price_under": price_under,
                "book_over": book_over,
                "book_under": book_under,
            }
        )
    return quotes


def generate_sample(slate, players):
    """Plausible-looking sample lines built from real recent shot totals.
    Not real sportsbook prices -- the frontend labels this mode clearly."""
    rng = random.Random(42)
    game_for_team = {}
    for g in slate:
        game_for_team[g["home_team"]] = g["game_id"]
        game_for_team[g["away_team"]] = g["game_id"]

    quotes = []
    for p in players:
        recent = [g["shots"] for g in p["games"][:10]]
        if len(recent) < SAMPLE_MIN_GAMES or p["team"] not in game_for_team:
            continue
        avg = sum(recent) / len(recent)
        if avg < SAMPLE_MIN_AVG_SHOTS:
            continue
        line = max(0.5, int(avg * rng.uniform(0.85, 1.15)) + 0.5)
        quotes.append(
            {
                "player_name": p["player_name"],
                "game_id": game_for_team[p["team"]],
                "point": line,
                "price_over": rng.choice([-130, -120, -115, -110, 100, 105, 115]),
                "price_under": rng.choice([-135, -115, -110, -105, 100, 110]),
                "book_over": "sample",
                "book_under": "sample",
            }
        )
    return quotes


def main():
    slate = (load_json("slate.json") or {}).get("games", [])
    players = load_json("players.json", [])
    api_key = os.environ.get("ODDS_API_KEY")
    source, quotes = "sample", []

    if not slate:
        print("No upcoming slate; writing empty odds file.")
    elif api_key:
        try:
            quotes = fetch_live(slate, api_key)
            if quotes:
                source = "live"
                print(f"  live quotes by book: {dict(Counter(q['book_over'] for q in quotes))}")
            else:
                print("Live odds returned no shot props; falling back to sample data.")
        except requests.RequestException as exc:
            print(f"Live odds fetch failed ({exc}); falling back to sample data.")

    if source == "sample" and slate:
        quotes = generate_sample(slate, players)

    write_json("odds_quotes.json", quotes)
    write_json("odds_meta.json", {"source": source, "fetched_at": utcnow_iso(), "quote_count": len(quotes)})
    print(f"Wrote {len(quotes)} odds quotes (source={source})")


if __name__ == "__main__":
    main()
