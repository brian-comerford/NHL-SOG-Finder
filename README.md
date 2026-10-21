# NHL SOG Finder

A static web app that projects NHL skaters' shots on goal from recent
performance and opponent shot suppression, compares that projection to
sportsbook shots-on-goal props, and surfaces the lines that look mispriced
(positive "edge").

It's deployed on **GitHub Pages**, which only serves static files, so there
is no server or database. A scheduled GitHub Action re-runs the data
pipeline once a day, builds the site, and deploys it.

**This is a statistical modeling tool, not betting advice.** Line changes,
scratches and goalie matchups move fast, and no model captures everything a
sportsbook prices in. Bet responsibly, or don't bet at all.

## How it works

```
scripts/fetch_stats.py   Finds the next game day's unstarted games, then pulls
                          rosters, skater game logs (this season + last) and
                          team shots-against from the NHL's free public API
                          (api-web.nhle.com / api.nhle.com -- no key needed).

scripts/fetch_matchups.py
                          Tallies shots on goal allowed to opposing LW / C /
                          RW / D for every team from final box scores and
                          ranks them 1 (fewest) to 32 (most). Box scores are
                          cached in data/cache/ (committed by CI), so after a
                          one-time backfill each run fetches only new games.

scripts/fetch_odds.py    Fetches player_shots_on_goal odds (DraftKings,
                          FanDuel) from The Odds API (needs ODDS_API_KEY).
                          Falls back to clearly-labeled SAMPLE lines built
                          from real player stats if no key is configured.

scripts/analyze.py       The value model:
                          1. Recency-weighted mean/variance of each skater's
                             shots over his last 40 games, last season
                             discounted.
                          2. Scaled by the opponent's shots allowed per game
                             to the player's position vs. league average
                             (shrunk toward last season, capped at +/-20%).
                          3. Over/under probability from a negative binomial
                             fit to the player's own variance (Poisson if
                             he's steadier than that).
                          4. Blended 40/60 with the book's no-vig price;
                             edge = blended - book. Ranked by edge.
                          Also snapshots every positive-edge pick to
                          data/history/ before puck drop.

scripts/grade.py         Grades past snapshots against final box scores
                          (scratched players are voided) and builds the
                          track record.

frontend/                React + Vite + Tailwind app. The Matchups tab (the
                          default) is the SOG-allowed-by-position grid for
                          the slate: tap a rank to see the opposing players
                          at that position with line, odds, edge and
                          confidence. The Edge list tab is the filterable
                          table of every prop ranked by edge.
```

Data flows one way: Python writes `data/*.json` -> the frontend build copies
it into `frontend/public/data/` -> Vite bundles the static site. Nothing is
fetched live from the browser, so the odds API key is never exposed.

## Running locally

```bash
cd scripts
pip install -r requirements.txt
export ODDS_API_KEY=your_key_here   # optional; omit for sample odds
python generate_data.py

cd ../frontend
npm install
npm run dev       # copies ../data/*.json into public/data, then starts Vite
```

## Deploying

`.github/workflows/deploy.yml` runs the pipeline, commits pick history back
to the repo, builds the frontend and deploys to GitHub Pages. It fires on
every push to `main`, daily at 9 AM Eastern, and on demand from the Actions tab.

1. **Settings -> Pages**: set **Source** to "GitHub Actions".
2. (Optional, for live odds) Get a free key at
   [the-odds-api.com](https://the-odds-api.com/) and add it as a repository
   secret named `ODDS_API_KEY` (**Settings -> Secrets and variables ->
   Actions**). Without it the site runs on sample lines.
3. Push to `main` or run the workflow manually.

The site will be at `https://brian-comerford.github.io/NHL-SOG-Finder/`.

Each run costs about one Odds API credit per game on the slate, so the
daily schedule fits in the free tier's 500 credits/month. Add a second run
only on a paid plan.

## Known limitations

- Line combinations, power-play units and the opposing goalie aren't
  modeled directly.
- The opponent adjustment is shots allowed per game by position, not split
  by score state or the opposing goalie.
- `MODEL_WEIGHT` (0.40) is borrowed from the NFL Player Prop Finder; refit
  it once enough NHL picks are graded (snapshots store the raw model
  probability for exactly that).
