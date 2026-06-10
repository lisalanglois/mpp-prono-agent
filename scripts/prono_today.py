#!/usr/bin/env python3
"""
Pronostics CDM 2026 du jour — données ESPN + forme récente.

Usage:
  python scripts/prono_today.py              # matchs des 3 prochains jours
  python scripts/prono_today.py --days 1     # aujourd'hui seulement
  python scripts/prono_today.py --match "Mexico" "South Africa"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from mpp.data.espn import fetch_upcoming_days, form_string_to_points
from mpp.data.loader import load_matches_csv, team_goals_stats, head_to_head
from mpp.predict import analyze_match


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FORM_CSV = DATA_DIR / "cdm2026_form.csv"


def blend_lambdas_with_form(
    lambda_home: float,
    lambda_away: float,
    home_form: str,
    away_form: str,
) -> tuple[float, float]:
    """Ajuste λ selon la forme ESPN (WWWDD) si disponible."""
    hf = form_string_to_points(home_form) / 3.0  # 0–1
    af = form_string_to_points(away_form) / 3.0
    # Légère modulation : forme forte +5 % attaque, faible -5 %
    lh = lambda_home * (0.95 + 0.10 * hf)
    la = lambda_away * (0.95 + 0.10 * af)
    return lh, la


def run_prediction(match: dict, matches_df: pd.DataFrame) -> None:
    home, away = match["home"], match["away"]
    odds = match.get("odds")

    result = analyze_match(
        home=home,
        away=away,
        matches_df=matches_df,
        competition=None,
        odds=odds,
        recent_n=10,
    )

    # Ajustement forme ESPN si stats CSV disponibles
    if match.get("home_form") or match.get("away_form"):
        lh, la = blend_lambdas_with_form(
            result.lambda_home,
            result.lambda_away,
            match.get("home_form", ""),
            match.get("away_form", ""),
        )
        from mpp.models.poisson import score_matrix, outcome_probabilities, top_exact_scores
        from mpp.mpp_strategy import pick_mpp_score

        matrix = score_matrix(lh, la)
        result.lambda_home, result.lambda_away = lh, la
        result.outcome_probs = outcome_probabilities(matrix)
        result.top_scores = top_exact_scores(matrix, 10)
        result.stat_score, result.stat_prob = result.top_scores[0]
        mpp_s, mpp_p, mpp_j = pick_mpp_score(
            result.top_scores, result.confidence, result.outcome_probs
        )
        result.mpp_score, result.mpp_prob, result.mpp_justification = mpp_s, mpp_p, mpp_j
        result.method += "+forme ESPN"

    print(f"\n📅 Coup d'envoi : {match['kickoff'][:16]} UTC | {match.get('venue', '')}")
    if odds:
        print(
            f"📊 Cotes ESPN (déc.) : 1={odds['home']:.2f} | N={odds['draw']:.2f} | 2={odds['away']:.2f}"
            f" | O/U {match.get('over_under', '?')}"
        )
    if match.get("home_form"):
        print(f"📈 Forme : {home} [{match['home_form']}] vs {away} [{match.get('away_form', '?')}]")

    result.display()

    h2h = head_to_head(matches_df, home, away) if not matches_df.empty else pd.DataFrame()
    if not h2h.empty:
        print("\n--- Confrontations directes ---")
        cols = [c for c in ["date", "home_team", "away_team", "home_goals", "away_goals"] if c in h2h.columns]
        print(h2h[cols].to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Pronostics MPP CDM 2026 — données du jour")
    parser.add_argument("--days", type=int, default=3, help="Jours à couvrir")
    parser.add_argument("--match", nargs=2, metavar=("HOME", "AWAY"), help="Filtrer un match")
    args = parser.parse_args()

    matches_df = load_matches_csv(FORM_CSV) if FORM_CSV.exists() else pd.DataFrame()

    print("=" * 60)
    print("⚠️  PRONOSTICS PROBABILISTES — CDM 2026")
    print(f"📁 Forme récente : {FORM_CSV.name} ({len(matches_df)} matchs)")
    print(f"🌐 Cotes + calendrier : ESPN (live)")
    print("=" * 60)

    upcoming = fetch_upcoming_days(args.days)
    if not upcoming:
        print("\n❌ Aucun match CDM trouvé sur la période.")
        print("   La CDM démarre le 11 juin — vérifie --days ou la date système.")
        return

    if args.match:
        h_filter, a_filter = args.match[0].lower(), args.match[1].lower()
        upcoming = [
            m
            for m in upcoming
            if h_filter in m["home"].lower() or a_filter in m["away"].lower()
        ]

    if not upcoming:
        print(f"\n❌ Match non trouvé : {args.match}")
        return

    for match in upcoming:
        if match["status"] not in ("Scheduled", "Scheduled", ""):
            continue
        run_prediction(match, matches_df)

    print("\n" + "=" * 60)
    print("💡 Rappel MPP : valide tes pronos avant le coup d'envoi.")
    print("   Score exact = cote × indice rareté si tu as le bon résultat.")
    print("=" * 60)


if __name__ == "__main__":
    main()
