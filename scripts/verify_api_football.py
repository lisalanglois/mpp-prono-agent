#!/usr/bin/env python3
"""
Vérifie les pronos via API-Football (Predictions + Odds).

Limite plan Free :
  - 100 requêtes / jour
  - Saisons 2022–2024 uniquement (pas CDM 2026 pour l'instant)

Usage:
  export API_FOOTBALL_KEY=...   # ou fichier .env
  python scripts/verify_api_football.py
  python scripts/verify_api_football.py --fixture 1234567
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

# Charger .env si présent
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if line.startswith("API_FOOTBALL_KEY="):
            os.environ.setdefault("API_FOOTBALL_KEY", line.split("=", 1)[1].strip())

API_BASE = "https://v3.football.api-sports.io"
WC_LEAGUE_ID = 1  # FIFA World Cup


def headers() -> dict[str, str]:
    key = os.environ.get("API_FOOTBALL_KEY", "")
    if not key:
        raise SystemExit("❌ API_FOOTBALL_KEY manquante (.env ou variable d'environnement)")
    return {"x-apisports-key": key}


def api_get(endpoint: str, params: dict) -> dict:
    time.sleep(0.6)  # respecter rate limit (~10 req/min sur free)
    r = requests.get(f"{API_BASE}/{endpoint}", headers=headers(), params=params, timeout=30)
    data = r.json()
    if data.get("errors"):
        return {"error": data["errors"], "response": []}
    return data


def check_status() -> dict:
    resp = api_get("status", {}).get("response", {})
    return resp if isinstance(resp, dict) else {}


def fetch_wc_fixtures(season: int) -> list[dict]:
    data = api_get("fixtures", {"league": WC_LEAGUE_ID, "season": season})
    if data.get("error"):
        return [{"error": data["error"]}]
    return data.get("response", [])


def fetch_prediction(fixture_id: int) -> dict | None:
    data = api_get("predictions", {"fixture": fixture_id})
    if not data.get("response"):
        return None
    item = data["response"][0]
    pred = item.get("predictions", {})
    teams = item.get("teams", {})
    return {
        "home": teams.get("home", {}).get("name", "?"),
        "away": teams.get("away", {}).get("name", "?"),
        "percent": pred.get("percent", {}),
        "advice": pred.get("advice", ""),
        "winner": pred.get("winner", {}),
        "goals_home": pred.get("goals", {}).get("home"),
        "goals_away": pred.get("goals", {}).get("away"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--fixture", type=int, help="Tester une fixture précise")
    parser.add_argument("--max", type=int, default=10, help="Max prédictions à fetcher")
    args = parser.parse_args()

    status = check_status()
    sub = status.get("subscription", {})
    reqs = status.get("requests", {})
    print("=" * 60)
    print("API-Football — vérification")
    print(f"Plan : {sub.get('plan')} | Requêtes : {reqs.get('current')}/{reqs.get('limit_day')}")
    print("=" * 60)

    if args.fixture:
        pred = fetch_prediction(args.fixture)
        if pred:
            print(f"\n{pred['home']} vs {pred['away']}")
            print(f"  % : {pred['percent']}")
            print(f"  Conseil API : {pred['advice']}")
            print(f"  Buts estimés : {pred['goals_home']} - {pred['goals_away']}")
        else:
            print("❌ Pas de prédiction pour cette fixture")
        return

    print(f"\n🔍 Recherche matchs CDM (league={WC_LEAGUE_ID}, season={args.season})...")
    fixtures = fetch_wc_fixtures(args.season)

    if fixtures and fixtures[0].get("error"):
        err = fixtures[0]["error"]
        print(f"\n❌ CDM {args.season} non accessible : {err}")
        print("\n📌 Plan Free = saisons 2022–2024 seulement.")
        print("   La CDM 2026 n'est pas encore dispo sur ton plan gratuit.")
        print("\n✅ Alternatives actuelles :")
        print("   • ESPN (déjà utilisé dans prono_today.py)")
        print("   • Points MPP + modèle Poisson du projet")
        print("   • Upgrade API-Football quand la saison 2026 sera ouverte")
        return

    print(f"✅ {len(fixtures)} matchs trouvés")
    for item in fixtures[: args.max]:
        fid = item["fixture"]["id"]
        home = item["teams"]["home"]["name"]
        away = item["teams"]["away"]["name"]
        pred = fetch_prediction(fid)
        if pred:
            print(f"\n{home} vs {away} (fixture {fid})")
            print(f"  % : {pred['percent']}")
            print(f"  Conseil : {pred['advice']}")


if __name__ == "__main__":
    main()
