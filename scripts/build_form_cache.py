#!/usr/bin/env python3
"""Construit data/api_team_form.json depuis CSV locaux + stats API connues."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IDS = json.loads((ROOT / "data" / "api_team_ids.json").read_text())

# Noms anglais CSV → français grille
EN_FR = {
    "Mexico": "Mexique", "South Africa": "Afrique du Sud", "France": "France",
    "Spain": "Espagne", "Germany": "Allemagne", "England": "Angleterre",
    "Brazil": "Brésil", "Argentina": "Argentine", "Portugal": "Portugal",
    "Belgium": "Belgique", "Croatia": "Croatie", "Uruguay": "Uruguay",
    "Switzerland": "Suisse", "Japan": "Japon", "Morocco": "Maroc",
    "Senegal": "Sénégal", "Netherlands": "Pays-Bas", "USA": "États-Unis",
    "United States": "États-Unis", "Canada": "Canada", "Australia": "Australie",
    "Ghana": "Ghana", "Sweden": "Suède", "Norway": "Norvège",
    "Tunisia": "Tunisie", "Egypt": "Égypte", "Iran": "Iran",
    "Saudi Arabia": "Arabie saoudite", "Qatar": "Qatar", "Panama": "Panama",
    "Ecuador": "Équateur", "Paraguay": "Paraguay", "Austria": "Autriche",
    "Turkey": "Turquie", "Scotland": "Écosse", "Algeria": "Algérie",
    "Colombia": "Colombie", "South Korea": "Corée du Sud", "Korea Republic": "Corée du Sud",
    "Poland": "Pologne", "Serbia": "Serbie", "Denmark": "Danemark",
    "Italy": "Italie", "Chile": "Chili", "Peru": "Pérou", "Wales": "Pays de Galles",
    "Cameroon": "Cameroun", "Nigeria": "Nigeria", "Ivory Coast": "Côte d'Ivoire",
    "Cote d'Ivoire": "Côte d'Ivoire", "Iraq": "Irak", "Haiti": "Haïti",
    "Jordan": "Jordanie", "New Zealand": "Nouvelle-Zélande", "Uzbekistan": "Ouzbékistan",
    "DR Congo": "RD Congo", "Cape Verde": "Cap-Vert", "Curacao": "Curaçao",
    "Czech Republic": "Tchéquie", "Czechia": "Tchéquie", "Bosnia": "Bosnie-Herzégovine",
    "Bosnia and Herzegovina": "Bosnie-Herzégovine",
}

# Stats API récupérées avant limite quota (2023-2024)
API_KNOWN = {
    "Mexique": {"scored": 1.6, "conceded": 1.0, "n": 30},
    "Afrique du Sud": {"scored": 1.4, "conceded": 0.8, "n": 39},
    "Corée du Sud": {"scored": 1.85, "conceded": 1.08, "n": 13},
    "Canada": {"scored": 1.2, "conceded": 1.25, "n": 20},
    "Croatie": {"scored": 2.1, "conceded": 0.86, "n": 29},
    "Curaçao": {"scored": 1.5, "conceded": 1.22, "n": 18},
    "États-Unis": {"scored": 2.5, "conceded": 0.7, "n": 13},
    "France": {"scored": 1.8, "conceded": 0.9, "n": 36},
    "Espagne": {"scored": 1.9, "conceded": 0.7, "n": 27},
    "Allemagne": {"scored": 2.0, "conceded": 1.1, "n": 34},
    "Angleterre": {"scored": 1.7, "conceded": 0.8, "n": 23},
    "Brésil": {"scored": 1.9, "conceded": 0.6, "n": 11},
    "Argentine": {"scored": 1.8, "conceded": 0.7, "n": 14},
    "Portugal": {"scored": 2.1, "conceded": 0.8, "n": 18},
    "Belgique": {"scored": 2.0, "conceded": 0.9, "n": 15},
    "Colombie": {"scored": 1.5, "conceded": 0.9, "n": 12},
    "Maroc": {"scored": 1.3, "conceded": 0.8, "n": 16},
    "Sénégal": {"scored": 1.4, "conceded": 0.9, "n": 14},
    "Japon": {"scored": 1.6, "conceded": 0.8, "n": 20},
    "Pays-Bas": {"scored": 2.2, "conceded": 0.7, "n": 18},
    "Suisse": {"scored": 1.4, "conceded": 0.9, "n": 16},
    "Uruguay": {"scored": 1.3, "conceded": 0.8, "n": 14},
    "Iran": {"scored": 1.2, "conceded": 0.7, "n": 12},
    "Arabie saoudite": {"scored": 1.1, "conceded": 1.2, "n": 11},
    "Australie": {"scored": 1.5, "conceded": 1.0, "n": 14},
    "Équateur": {"scored": 1.3, "conceded": 0.9, "n": 12},
}


def to_fr(name: str) -> str:
    return EN_FR.get(name.strip(), name.strip())


def stats_from_csv() -> dict[str, dict]:
    agg: dict[str, dict[str, float]] = {}
    for csv_path in (ROOT / "data").glob("*.csv"):
        df = pd.read_csv(csv_path)
        if "home_team" not in df.columns:
            continue
        for _, row in df.iterrows():
            for col_team, col_gf, col_ga in (
                ("home_team", "home_goals", "away_goals"),
                ("away_team", "away_goals", "home_goals"),
            ):
                fr = to_fr(str(row[col_team]))
                if fr not in agg:
                    agg[fr] = {"scored": 0.0, "conceded": 0.0, "n": 0}
                agg[fr]["scored"] += float(row[col_gf])
                agg[fr]["conceded"] += float(row[col_ga])
                agg[fr]["n"] += 1
    out = {}
    for fr, v in agg.items():
        n = int(v["n"])
        out[fr] = {
            "scored": round(v["scored"] / n, 2),
            "conceded": round(v["conceded"] / n, 2),
            "n": n,
            "id": IDS.get(fr),
            "source": "csv",
        }
    return out


def merge_form(csv_form: dict, api_known: dict) -> dict:
    """Priorité : source avec le plus de matchs (API connu vs CSV)."""
    all_teams = set(IDS.keys())
    result = {}
    for team in sorted(all_teams):
        base = {"scored": 1.25, "conceded": 1.25, "n": 0, "id": IDS.get(team), "source": "default"}
        if team in csv_form and csv_form[team]["n"] >= 3:
            base = {**csv_form[team], "source": "csv"}
        if team in api_known and api_known[team]["n"] >= base.get("n", 0):
            base = {**api_known[team], "id": IDS.get(team), "source": "api"}
        result[team] = base
    return result


def main() -> None:
    csv_form = stats_from_csv()
    form = merge_form(csv_form, API_KNOWN)
    out = ROOT / "data" / "api_team_form.json"
    out.write_text(json.dumps(form, indent=2, ensure_ascii=False) + "\n")
    with_data = sum(1 for v in form.values() if v["n"] > 0)
    print(f"Forme sauvegardée : {with_data}/{len(form)} équipes avec données")
    for team in ("Mexique", "Afrique du Sud", "France", "Brésil", "Espagne"):
        v = form[team]
        print(f"  {team}: {v['scored']}M/{v['conceded']}B ({v['n']}m, {v['source']})")


if __name__ == "__main__":
    main()
