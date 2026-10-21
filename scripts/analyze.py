"""The value model: projects each skater's shots on goal, prices the
over/under against the sportsbook line, and ranks props by edge.

1. Baseline: recency-weighted mean and variance of the skater's shots per
   game over his last MAX_GAMES games (this season + last season, with
   last season discounted -- see common.game_weights).
2. Opponent: scales the mean by how many shots the opponent allows per
   game *to the player's position* relative to league average (see
   fetch_matchups.py), falling back to team-wide shots allowed.
3. Distribution: shots are counts and are overdispersed (a top-line
   shooter's 2-shot nights and 7-shot nights are both common), so the
   projection is a negative binomial with the player's own variance-to-
   mean ratio, falling back to Poisson when he's steadier than that.
4. Edge: the model's probability is blended with the book's no-vig
   probability (MODEL_WEIGHT), and edge = blended - book.

Writes data/props.json, data/meta.json and data/matchups.json (the
position-ranking grid for the slate), and snapshots the current
recommendations to data/history/ for grading once the games are played.
"""
import os

from scipy.stats import nbinom, poisson

from common import (
    HISTORY_DIR,
    POSITION_LABELS,
    american_to_implied_prob,
    game_weights,
    load_json,
    normalize_name,
    remove_vig_two_way,
    safe_round,
    utcnow_iso,
    weighted_mean_var,
    write_json,
)

MAX_GAMES = 40
MIN_GAMES = 5
# How much the final probability trusts the stat model vs. the market's
# no-vig price. A raw per-player model is overconfident on its own -- the
# market already prices in line changes, injuries and goalie matchups the
# model can't see -- so the market gets the majority vote. 0.40 mirrors
# the NFL Player Prop Finder's tuned weight; refit it once enough NHL
# picks are graded (snapshots keep raw_model_prob for exactly that).
MODEL_WEIGHT = 0.40
# Opponent shots-against is shrunk toward last season (or league average)
# with this many games' worth of weight, and clipped -- even the leakiest
# defense doesn't turn a 2-shot player into a 3-shot player.
OPP_SHRINK_GAMES = 15
OPP_FACTOR_BOUNDS = (0.85, 1.15)
MAX_DISPERSION = 2.5
# A skater whose team has played this many games since his last one is
# treated as injured / scratched / sent down and left out entirely.
INACTIVE_TEAM_GAMES_MISSED = 4

TREND_WINDOW = 10
TREND_MIN_HIT_RATE = 0.7
MATCHUP_MIN_GAMES = 3


def league_and_opponent_factors(team_stats):
    current = team_stats.get("current", {})
    previous = team_stats.get("previous", {})

    def avg(rows):
        vals = [r["shots_against_pg"] for r in rows.values() if r.get("shots_against_pg")]
        return sum(vals) / len(vals) if vals else None

    league_prev = avg(previous)
    league_cur = avg(current) or league_prev
    if not league_cur:
        return {}

    factors = {}
    for team in set(current) | set(previous):
        cur = current.get(team, {})
        prior = previous.get(team, {}).get("shots_against_pg") or league_prev or league_cur
        gp = cur.get("games_played") or 0
        sa = cur.get("shots_against_pg") or prior
        blended = (gp * sa + OPP_SHRINK_GAMES * prior) / (gp + OPP_SHRINK_GAMES)
        lg = (gp * league_cur + OPP_SHRINK_GAMES * (league_prev or league_cur)) / (gp + OPP_SHRINK_GAMES)
        lo, hi = OPP_FACTOR_BOUNDS
        factors[team] = min(max(blended / lg, lo), hi)
    return factors


def team_game_dates(players, season):
    """team -> sorted list of this season's game dates, pieced together from
    the union of every rostered teammate's game log (no extra API calls)."""
    dates = {}
    for p in players:
        for g in p["games"]:
            if g["season"] == season and g["team"] == p["team"]:
                dates.setdefault(p["team"], set()).add(g["date"])
    return {t: sorted(d) for t, d in dates.items()}


def team_games_missed(player, season, team_dates):
    dates = team_dates.get(player["team"], [])
    current = [g for g in player["games"] if g["season"] == season]
    if not current:
        return len(dates)
    last = current[0]["date"]
    return sum(1 for d in dates if d > last)


def over_under_probs(mean, dispersion, line):
    """P(over), P(under) for a count with this mean and variance/mean
    ratio. Whole-number lines can push; a push refunds the bet, so the
    probabilities are renormalized over the non-push outcomes."""
    mean = max(mean, 0.05)
    if dispersion <= 1.01:
        dist = poisson(mean)
    else:
        var = mean * dispersion
        dist = nbinom(mean**2 / (var - mean), mean / var)
    if float(line).is_integer():
        p_under = dist.cdf(line - 1)
        p_over = 1 - dist.cdf(line)
        total = p_over + p_under
        return p_over / total, p_under / total
    p_over = 1 - dist.cdf(int(line))
    return p_over, 1 - p_over


def blend(model_prob, market_prob):
    if market_prob is None:
        return model_prob
    return MODEL_WEIGHT * model_prob + (1 - MODEL_WEIGHT) * market_prob


def hit(side, line, value):
    return value > line if side == "over" else value < line


def build_trends(games, line, side, opponent):
    trends = []
    recent = games[:TREND_WINDOW]
    hits = sum(hit(side, line, g["shots"]) for g in recent)
    if len(recent) >= 5 and hits / len(recent) >= TREND_MIN_HIT_RATE:
        trends.append(f"{side.title()} {line} in {hits} of his last {len(recent)} games")

    streak = 0
    for g in games:
        if not hit(side, line, g["shots"]):
            break
        streak += 1
    if streak >= 4 and streak > hits:
        trends.append(f"{side.title()} {line} in {streak} straight games")

    vs = [g for g in games if g["opponent"] == opponent]
    vs_hits = sum(hit(side, line, g["shots"]) for g in vs)
    if len(vs) >= MATCHUP_MIN_GAMES and vs_hits / len(vs) >= TREND_MIN_HIT_RATE:
        trends.append(f"{side.title()} {line} in {vs_hits} of {len(vs)} recent games vs {opponent}")

    toi_recent = [g["toi"] for g in games[:5] if g["toi"]]
    toi_prior = [g["toi"] for g in games[5:20] if g["toi"]]
    if len(toi_recent) >= 3 and len(toi_prior) >= 5:
        r, p = sum(toi_recent) / len(toi_recent), sum(toi_prior) / len(toi_prior)
        if r >= p * 1.1:
            trends.append(f"Ice time up: {r:.1f} min/game over his last 5, vs {p:.1f} before")
        elif r <= p * 0.9:
            trends.append(f"Ice time down: {r:.1f} min/game over his last 5, vs {p:.1f} before")
    return trends


def confidence_for(games, season, side, line, edge, opp_factor, opp_rank=None, rank_of=32):
    """Low/Medium/High from a handful of transparent signals, each listed
    for the detail view as supporting or cutting against the pick."""
    reasons = []
    n = len(games)
    n_current = sum(1 for g in games if g["season"] == season)
    recent = games[:TREND_WINDOW]
    hit_rate = sum(hit(side, line, g["shots"]) for g in recent) / len(recent)

    if n < 12:
        reasons.append((False, f"Thin sample: only {n} games behind the projection"))
    if n_current < 3:
        reasons.append((False, f"Only {n_current} game(s) this season -- leaning on last season"))

    pct = round(hit_rate * 100)
    if hit_rate >= 0.6:
        reasons.append((True, f"Recent form agrees: {side} hit in {pct}% of his last {len(recent)} games"))
    elif hit_rate <= 0.4:
        reasons.append((False, f"Recent form disagrees: {side} hit in only {pct}% of his last {len(recent)}"))

    matchup = f"opponent allows {opp_factor:.2f}x league-average shots"
    if opp_rank is not None:
        matchup += f" to his position (rank {opp_rank} of {rank_of})"
    if (opp_factor > 1.03 and side == "over") or (opp_factor < 0.97 and side == "under"):
        reasons.append((True, f"Matchup helps: {matchup}"))
    elif (opp_factor > 1.03 and side == "under") or (opp_factor < 0.97 and side == "over"):
        reasons.append((False, f"Matchup hurts: {matchup}"))

    toi_recent = [g["toi"] for g in games[:5] if g["toi"]]
    toi_all = [g["toi"] for g in games[:20] if g["toi"]]
    if len(toi_recent) >= 3 and toi_all:
        ratio = (sum(toi_recent) / len(toi_recent)) / (sum(toi_all) / len(toi_all))
        if ratio < 0.88:
            reasons.append((side == "under", "Ice time has dropped over his last 5 games"))
        elif ratio > 1.12:
            reasons.append((side == "over", "Ice time has risen over his last 5 games"))

    if edge >= 0.06:
        reasons.append((True, f"Large edge ({edge * 100:.1f}%)"))

    # High needs at least two more signals for the pick than against it,
    # and one of them has to be the player's own recent results -- a big
    # edge with a cold shooter is exactly where the model tends to be
    # wrong.
    score = sum(1 if s else -1 for s, _ in reasons)
    if score >= 2 and hit_rate >= 0.6 and n >= 15:
        label = "High"
    elif score >= 0:
        label = "Medium"
    else:
        label = "Low"
    reasons.sort(key=lambda r: not r[0])
    return label, [{"supports": s, "text": t} for s, t in reasons]


def match_player(name, candidates):
    key = normalize_name(name)
    for p in candidates:
        if normalize_name(p["player_name"]) == key:
            return p
    # Fallback for nickname/abbreviation mismatches ("Alex" vs "Alexander",
    # "J.J." vs "JJ"): same last name + first initial within the two teams.
    parts = name.split()
    if len(parts) >= 2:
        last, initial = normalize_name(parts[-1]), normalize_name(parts[0])[:1]
        hits = [
            p
            for p in candidates
            if normalize_name(p["player_name"].split()[-1]) == last
            and normalize_name(p["player_name"])[:1] == initial
        ]
        if len(hits) == 1:
            return hits[0]
    return None


def snapshot_picks(props, slate_date):
    """data/history/picks_{date}.json: the current recommendation for every
    prop, graded by grade.py once the game is final.

    Merged rather than overwritten: once a game starts, books pull its
    props and it drops out of this run's slate, but its last pre-game
    snapshot is exactly what should be graded -- so games absent from this
    run keep whatever was last recorded for them."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    name = f"history/picks_{slate_date}.json"
    fresh_games = {p["game_id"] for p in props}
    previous = load_json(name, {}) or {}
    carried = [pick for pick in previous.get("picks", []) if pick["game_id"] not in fresh_games]
    fresh = [
        {
            "game_id": p["game_id"],
            "player_id": p["player_id"],
            "player_name": p["player_name"],
            "position": p["position"],
            "team": p["team"],
            "opponent": p["opponent"],
            "line": p["line"],
            "side": p["recommended_side"],
            "model_prob": p[f"model_prob_{p['recommended_side']}"],
            "raw_model_prob": p[f"raw_model_prob_{p['recommended_side']}"],
            "edge": p["recommended_edge"],
            "confidence": p["confidence"],
            "price": p[f"price_{p['recommended_side']}"],
            "book": p[f"book_{p['recommended_side']}"],
            "projected_sog": p["projected_sog"],
        }
        for p in props
        if p["recommended_edge"] > 0
    ]
    write_json(name, {"date": slate_date, "generated_at": utcnow_iso(), "picks": carried + fresh})


def main():
    slate_meta = load_json("slate.json", {}) or {}
    slate = slate_meta.get("games", [])
    season = slate_meta.get("season")
    players = load_json("players.json", [])
    quotes = load_json("odds_quotes.json", [])
    odds_meta = load_json("odds_meta.json", {}) or {}
    opp_factors = league_and_opponent_factors(load_json("team_stats.json", {}) or {})
    pos_defense = load_json("position_defense.json", {}) or {}
    pos_teams = pos_defense.get("teams", {})

    games_by_id = {g["game_id"]: g for g in slate}
    team_dates = team_game_dates(players, season)
    players_by_team = {}
    for p in players:
        players_by_team.setdefault(p["team"], []).append(p)

    props, inactive, unmatched = [], set(), 0
    for q in quotes:
        game = games_by_id.get(q["game_id"])
        if not game or q.get("point") is None:
            continue
        candidates = players_by_team.get(game["home_team"], []) + players_by_team.get(game["away_team"], [])
        player = match_player(q["player_name"], candidates)
        if not player:
            unmatched += 1
            continue
        if team_games_missed(player, season, team_dates) >= INACTIVE_TEAM_GAMES_MISSED:
            inactive.add(player["player_id"])
            continue
        games = player["games"][:MAX_GAMES]
        if len(games) < MIN_GAMES:
            continue

        home = player["team"] == game["home_team"]
        opponent = game["away_team"] if home else game["home_team"]
        weights = game_weights([g["season"] for g in games], season)
        mean, var, n = weighted_mean_var([g["shots"] for g in games], weights)
        toi_mean, _, _ = weighted_mean_var(
            [g["toi"] for g in games if g["toi"]], [w for g, w in zip(games, weights) if g["toi"]]
        )
        position = POSITION_LABELS.get(player["position"], player["position"])
        opp_pos = pos_teams.get(opponent, {}).get(position)
        opp_factor = opp_pos["factor"] if opp_pos else opp_factors.get(opponent, 1.0)
        projected = mean * opp_factor
        dispersion = min(max(var / mean, 1.0), MAX_DISPERSION) if mean > 0 else 1.0
        line = float(q["point"])
        raw_over, raw_under = over_under_probs(projected, dispersion, line)

        imp_over, imp_under = remove_vig_two_way(
            american_to_implied_prob(q["price_over"]), american_to_implied_prob(q["price_under"])
        )
        p_over, p_under = blend(raw_over, imp_over), blend(raw_under, imp_under)
        edge_over = p_over - imp_over if imp_over is not None else None
        edge_under = p_under - imp_under if imp_under is not None else None
        side = "over" if _or_floor(edge_over) >= _or_floor(edge_under) else "under"
        edge = (edge_over if side == "over" else edge_under) or 0.0
        confidence, reasons = confidence_for(
            games, season, side, line, edge, opp_factor,
            opp_pos["rank"] if opp_pos else None, pos_defense.get("team_count") or 32,
        )

        props.append(
            {
                "player_id": player["player_id"],
                "player_name": player["player_name"],
                "position": position,
                "team": player["team"],
                "opponent": opponent,
                "home": home,
                "game_id": game["game_id"],
                "matchup": f"{game['away_team']} @ {game['home_team']}",
                "start_time_utc": game["start_time_utc"],
                "line": line,
                "price_over": q["price_over"],
                "price_under": q["price_under"],
                "book_over": q["book_over"],
                "book_under": q["book_under"],
                "raw_model_prob_over": safe_round(raw_over),
                "raw_model_prob_under": safe_round(raw_under),
                "model_prob_over": safe_round(p_over),
                "model_prob_under": safe_round(p_under),
                "implied_prob_over": safe_round(imp_over),
                "implied_prob_under": safe_round(imp_under),
                "edge_over": safe_round(edge_over),
                "edge_under": safe_round(edge_under),
                "recommended_side": side,
                "recommended_edge": safe_round(edge),
                "projected_sog": round(projected, 2),
                "season_avg_sog": safe_round(
                    _avg([g["shots"] for g in games if g["season"] == season]), 2
                ),
                "avg_toi": safe_round(toi_mean, 1),
                "shots_per_60": safe_round(mean / toi_mean * 60, 1) if toi_mean else None,
                "opponent_factor": round(opp_factor, 3),
                "opponent_pos_rank": opp_pos["rank"] if opp_pos else None,
                "dispersion": round(dispersion, 2),
                "sample_games": n,
                "season_games": sum(1 for g in games if g["season"] == season),
                "confidence": confidence,
                "confidence_reasons": reasons,
                "trends": build_trends(games, line, side, opponent),
                "recent_games": [
                    {"date": g["date"], "opponent": g["opponent"], "home": g["home"], "shots": g["shots"], "toi": g["toi"]}
                    for g in games[:10]
                ],
            }
        )

    props.sort(key=lambda p: p["recommended_edge"], reverse=True)
    print(
        f"Built {len(props)} props ({unmatched} quotes unmatched to a roster, "
        f"{len(inactive)} inactive players excluded)"
    )

    write_json("props.json", props)
    write_json(
        "meta.json",
        {
            "generated_at": utcnow_iso(),
            "slate_date": slate_meta.get("slate_date"),
            "season": season,
            "game_count": len(slate),
            "odds_source": odds_meta.get("source", "sample"),
            "odds_fetched_at": odds_meta.get("fetched_at"),
            "prop_count": len(props),
            "inactive_players_excluded": len(inactive),
            "model_weight": MODEL_WEIGHT,
            "matchups": sorted({p["matchup"] for p in props}),
            "books": sorted({b for p in props for b in (p["book_over"], p["book_under"]) if b}),
        },
    )
    write_json(
        "matchups.json",
        {
            "slate_date": slate_meta.get("slate_date"),
            "season": season,
            "team_count": pos_defense.get("team_count", 0),
            "positions": pos_defense.get("positions", ["LW", "C", "RW", "D"]),
            "league_avg": pos_defense.get("league_avg", {}),
            "games": [
                {
                    "game_id": g["game_id"],
                    "start_time_utc": g["start_time_utc"],
                    "away_team": g["away_team"],
                    "home_team": g["home_team"],
                }
                for g in sorted(slate, key=lambda g: (g["start_time_utc"] or "", g["game_id"]))
            ],
            "teams": {
                t: pos_teams[t]
                for g in slate
                for t in (g["away_team"], g["home_team"])
                if t in pos_teams
            },
        },
    )
    if slate_meta.get("slate_date") and props:
        snapshot_picks(props, slate_meta["slate_date"])


def _or_floor(edge):
    return -1.0 if edge is None else edge


def _avg(values):
    return sum(values) / len(values) if values else None


if __name__ == "__main__":
    main()
