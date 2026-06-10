#!/usr/bin/env python3
"""
Export pronos du jour pour automatisation (GitHub Actions, GitHub Pages).

Sources : ESPN (cotes live) + forme CSV + overrides MPP.
Sorties :
  - data/daily_predictions.json  (matchs à venir sur N jours)
  - web/matches.json             (grille complète pour le site local)

Usage:
  python scripts/export_daily.py
  python scripts/export_daily.py --days 2 --stdout
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from export_web import OVERRIDES
from mpp.data.espn import fetch_upcoming_days, form_string_to_points
from mpp.data.loader import load_matches_csv
from mpp.data.team_aliases import to_french
from mpp.models.poisson import score_matrix, top_exact_scores, outcome_probabilities
from mpp.mpp_strategy import pick_mpp_score
from mpp_grille_cdm import analyze, fit_lambdas_from_decimal, pick_mpp_score_v2, _with_odds, MATCHES

FORM_CSV = ROOT / "data" / "cdm2026_form.csv"
DAILY_OUT = ROOT / "data" / "daily_predictions.json"


def blend_lambdas(lh: float, la: float, home_form: str, away_form: str) -> tuple[float, float]:
    hf = form_string_to_points(home_form) / 3.0
    af = form_string_to_points(away_form) / 3.0
    return lh * (0.95 + 0.10 * hf), la * (0.95 + 0.10 * af)


def predict_from_espn(event: dict, matches_df: pd.DataFrame) -> dict:
    home_fr = to_french(event["home"])
    away_fr = to_french(event["away"])
    key = f"{home_fr} - {away_fr}"

    if key in OVERRIDES:
        score = OVERRIDES[key]
        source = "override"
    else:
        # Chercher dans la grille MPP statique
        m = next((x for x in MATCHES if x.home == home_fr and x.away == away_fr), None)
        if m:
            m = _with_odds(m)
            r = analyze(m)
            score = r["score"]
            source = "grille_mpp"
        elif event.get("odds"):
            odds = event["odds"]
            lh, la, blend = fit_lambdas_from_decimal(odds["home"], odds["draw"], odds["away"])
            if event.get("home_form") or event.get("away_form"):
                lh, la = blend_lambdas(lh, la, event.get("home_form", ""), event.get("away_form", ""))
            matrix = score_matrix(lh, la)
            top = top_exact_scores(matrix, 12)
            probs = outcome_probabilities(matrix)
            score, _ = pick_mpp_score_v2(top, blend["home"], blend["draw"], blend["away"], 50, 25, 25)
            source = "espn_poisson"
        else:
            score = "1-1"
            source = "default"

    return {
        "match": key,
        "home": home_fr,
        "away": away_fr,
        "score": score,
        "kickoff_utc": event.get("kickoff"),
        "venue": event.get("venue"),
        "odds": event.get("odds"),
        "home_form": event.get("home_form"),
        "away_form": event.get("away_form"),
        "source": source,
        "mpp_copy": f"{home_fr} {score.replace('-', ' - ')} {away_fr}",
    }


def export_daily(days: int) -> dict:
    matches_df = load_matches_csv(FORM_CSV) if FORM_CSV.exists() else pd.DataFrame()
    upcoming = fetch_upcoming_days(days)
    predictions = []

    for event in upcoming:
        if event.get("status") not in ("Scheduled", "", None):
            continue
        try:
            predictions.append(predict_from_espn(event, matches_df))
        except Exception as exc:
            predictions.append({
                "match": f"{event.get('home')} - {event.get('away')}",
                "error": str(exc),
            })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "count": len(predictions),
        "disclaimer": "Pronostics probabilistes — à recopier manuellement sur mpp.football",
        "predictions": predictions,
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=2, help="Jours à couvrir")
    parser.add_argument("--stdout", action="store_true", help="Afficher JSON sur stdout")
    parser.add_argument("--skip-web", action="store_true", help="Ne pas régénérer web/matches.json")
    args = parser.parse_args()

    payload = export_daily(args.days)

    DAILY_OUT.parent.mkdir(exist_ok=True)
    DAILY_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not args.skip_web:
        from export_web import main as export_web_main
        export_web_main()

    if args.stdout:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"✅ {payload['count']} pronos → {DAILY_OUT}")
        for p in payload["predictions"]:
            if "error" in p:
                print(f"   ⚠️  {p['match']}: {p['error']}")
            else:
                print(f"   {p['kickoff_utc'][:16]} {p['match']}: {p['score']} ({p['source']})")


if __name__ == "__main__":
    main()
