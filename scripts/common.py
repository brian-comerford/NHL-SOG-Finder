"""Shared constants and helpers for the data pipeline."""
import datetime as dt
import json
import math
import os
import re
import time
import unicodedata
from zoneinfo import ZoneInfo

import numpy as np
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")

NHL_WEB_API = "https://api-web.nhle.com/v1"
NHL_STATS_API = "https://api.nhle.com/stats/rest/en"

# NHL "game days" are defined in Eastern time -- a 10:30 PM ET puck drop in
# Vancouver is still that day's slate, even though it's tomorrow in UTC.
NHL_TZ = ZoneInfo("America/New_York")

# Regular season and playoffs; preseason (1) is skipped -- lineups are
# mostly prospects and books barely post shot props for it.
GAME_TYPES = (2, 3)

# Recency/season weighting for player baselines -- see game_weights().
# Hockey seasons are 82 games, so the per-game decay is gentler than a
# football model's would be: game 10 back still counts ~45%, game 25 back
# ~13%.
RECENCY_DECAY = 0.93
# Extra multiplier on every game from last season, on top of the game-by-
# game decay. Keeps last season useful early in the year (when this
# season only has a handful of games) without letting it outweigh what a
# player is doing now -- new linemates, a new power-play role, or a new
# team change shot volume more than anything in last year's log.
SEASON_DECAY = 0.6


def game_weights(seasons, current_season):
    """Per-game weight: game-recency decay times the per-season penalty.
    `seasons` is most-recent-first, aligned with the values being weighted.
    Seasons are NHL ids like 20262027, so the start year is the first four
    digits."""
    current_start = int(str(current_season)[:4])
    return [
        RECENCY_DECAY**i * SEASON_DECAY ** max(0, current_start - int(str(s)[:4]))
        for i, s in enumerate(seasons)
    ]


def weighted_mean_var(values, weights):
    """`values`/`weights` aligned. Returns (mean, variance, n)."""
    n = len(values)
    if n == 0:
        return None, None, 0
    values = np.array(values, dtype=float)
    weights = np.array(weights, dtype=float)
    mean = float(np.average(values, weights=weights))
    var = float(np.average((values - mean) ** 2, weights=weights))
    return mean, var, n


def season_id_for(date):
    """NHL season id (e.g. 20262027) for a calendar date. Seasons start in
    October; anything from July on counts toward the upcoming season."""
    start = date.year if date.month >= 7 else date.year - 1
    return start * 10000 + start + 1


def previous_season_id(season_id):
    start = int(str(season_id)[:4]) - 1
    return start * 10000 + start + 1


def today_et():
    return dt.datetime.now(NHL_TZ).date()


def toi_to_minutes(toi):
    """'18:34' -> 18.57. Missing/malformed -> None."""
    if not toi or ":" not in str(toi):
        return None
    mins, secs = str(toi).split(":", 1)
    try:
        return int(mins) + int(secs) / 60.0
    except ValueError:
        return None


_session = requests.Session()
_session.headers["User-Agent"] = "nhl-sog-finder (github.com/brian-comerford/NHL-SOG-Finder)"


def get_json(url, params=None, retries=3, timeout=30):
    """GET with a couple of retries -- the NHL API occasionally 5xx's or
    times out under load, and one blip shouldn't fail the whole run."""
    for attempt in range(retries):
        try:
            resp = _session.get(url, params=params, timeout=timeout)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    return None


def load_json(name, default=None):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def write_json(name, payload):
    path = os.path.join(DATA_DIR, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f)


def normalize_name(name):
    """Accent- and punctuation-insensitive key, so "Tim Stützle" (NHL API)
    and "Tim Stutzle" (sportsbook) or "St. Louis Blues" / "St Louis Blues"
    match."""
    ascii_name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", ascii_name.lower())


# NHL abbreviations -> full names as sportsbook feeds (The Odds API) spell
# them. Used to match odds events to the NHL schedule, alongside the
# schedule's own place + common name.
TEAM_CODE_TO_NAME = {
    "ANA": "Anaheim Ducks",
    "BOS": "Boston Bruins",
    "BUF": "Buffalo Sabres",
    "CAR": "Carolina Hurricanes",
    "CBJ": "Columbus Blue Jackets",
    "CGY": "Calgary Flames",
    "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche",
    "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings",
    "EDM": "Edmonton Oilers",
    "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings",
    "MIN": "Minnesota Wild",
    "MTL": "Montreal Canadiens",
    "NJD": "New Jersey Devils",
    "NSH": "Nashville Predators",
    "NYI": "New York Islanders",
    "NYR": "New York Rangers",
    "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers",
    "PIT": "Pittsburgh Penguins",
    "SEA": "Seattle Kraken",
    "SJS": "San Jose Sharks",
    "STL": "St Louis Blues",
    "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs",
    "UTA": "Utah Mammoth",
    "VAN": "Vancouver Canucks",
    "VGK": "Vegas Golden Knights",
    "WPG": "Winnipeg Jets",
    "WSH": "Washington Capitals",
}

POSITION_LABELS = {"C": "C", "L": "LW", "R": "RW", "D": "D"}


def american_to_implied_prob(odds):
    """Raw (vig-included) implied probability of American odds."""
    if odds is None:
        return None
    odds = float(odds)
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def remove_vig_two_way(prob_a, prob_b):
    """Normalize two complementary raw implied probabilities to remove vig."""
    if prob_a is None or prob_b is None:
        return prob_a, prob_b
    total = prob_a + prob_b
    if total <= 0:
        return prob_a, prob_b
    return prob_a / total, prob_b / total


def prob_to_american(p):
    """American odds that exactly imply probability p (no vig)."""
    p = min(max(p, 0.01), 0.99)
    if p >= 0.5:
        return round(-100 * p / (1 - p))
    return round(100 * (1 - p) / p)


def pick_units(price, hit):
    """Profit/loss in units for a flat 1-unit bet at these American odds.
    None if the price wasn't recorded, so callers can leave it out of a
    units total instead of guessing."""
    if price is None:
        return None
    price = float(price)
    if not hit:
        return -1.0
    return round(price / 100.0, 4) if price > 0 else round(100.0 / -price, 4)


def utcnow_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_round(x, digits=4):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, digits)
