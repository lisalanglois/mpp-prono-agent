#!/usr/bin/env python3
"""CLI — Analyse probabiliste d'un match pour Mon Petit Prono."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ajouter src au path pour exécution directe
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mpp.data.loader import load_matches_csv
from mpp.predict import analyze_match


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pronostic probabiliste MPP — jamais une certitude."
    )
    parser.add_argument("--home", required=True, help="Équipe domicile")
    parser.add_argument("--away", required=True, help="Équipe extérieur")
    parser.add_argument("--competition", default=None, help="Compétition (filtre)")
    parser.add_argument(
        "--data",
        default=None,
        help="Chemin CSV historique (football-data.co.uk ou format custom)",
    )
    parser.add_argument("--odds-home", type=float, default=None, help="Cote victoire domicile")
    parser.add_argument("--odds-draw", type=float, default=None, help="Cote match nul")
    parser.add_argument("--odds-away", type=float, default=None, help="Cote victoire extérieur")
    parser.add_argument("--recent", type=int, default=10, help="Matchs récents à considérer")
    args = parser.parse_args()

    matches_df = None
    if args.data:
        path = Path(args.data)
        if not path.exists():
            # Chercher dans data/ du projet
            alt = Path(__file__).resolve().parents[1] / "data" / args.data
            path = alt if alt.exists() else path
        matches_df = load_matches_csv(path)

    odds = None
    if args.odds_home and args.odds_draw and args.odds_away:
        odds = {"home": args.odds_home, "draw": args.odds_draw, "away": args.odds_away}

    result = analyze_match(
        home=args.home,
        away=args.away,
        matches_df=matches_df,
        competition=args.competition,
        odds=odds,
        recent_n=args.recent,
    )
    result.display()

    if not result.home_recent.empty:
        print("\n--- Derniers matchs (équipe domicile) ---")
        cols = [c for c in ["date", "home_team", "away_team", "home_goals", "away_goals"] if c in result.home_recent.columns]
        print(result.home_recent[cols].head(5).to_string(index=False))

    if not result.away_recent.empty:
        print("\n--- Derniers matchs (équipe extérieur) ---")
        cols = [c for c in ["date", "home_team", "away_team", "home_goals", "away_goals"] if c in result.away_recent.columns]
        print(result.away_recent[cols].head(5).to_string(index=False))

    if not result.h2h.empty:
        print("\n--- Confrontations directes ---")
        cols = [c for c in ["date", "home_team", "away_team", "home_goals", "away_goals"] if c in result.h2h.columns]
        print(result.h2h[cols].head(5).to_string(index=False))


if __name__ == "__main__":
    main()
