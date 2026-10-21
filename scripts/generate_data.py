"""Runs the full data pipeline: stats -> position defense -> odds -> model
-> grading.

Usage: python scripts/generate_data.py
Set ODDS_API_KEY for live odds; without it the site runs on clearly-
labeled sample lines built from real player stats.
"""
import analyze
import fetch_matchups
import fetch_odds
import fetch_stats
import grade


def main():
    print("== 1/5 fetching slate, rosters & game logs ==")
    fetch_stats.main()
    print("\n== 2/5 tallying shots allowed by position ==")
    fetch_matchups.main()
    print("\n== 3/5 fetching odds ==")
    fetch_odds.main()
    print("\n== 4/5 running shots-on-goal model ==")
    analyze.main()
    print("\n== 5/5 grading past picks ==")
    grade.main()


if __name__ == "__main__":
    main()
