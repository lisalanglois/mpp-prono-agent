#!/usr/bin/env python3
"""Exporte la grille CDM vers web/matches.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mpp_grille_cdm import MATCHES, analyze

# Noms canoniques (ESPN / MPP peuvent varier)
TEAM_CANONICAL: dict[str, str] = {
    "Türkiye": "Turquie",
    "Turkiye": "Turquie",
}


def canonical_team(name: str) -> str:
    return TEAM_CANONICAL.get(name.strip(), name.strip())


def match_key(home: str, away: str) -> str:
    return f"{canonical_team(home)} - {canonical_team(away)}"


def get_user_score(home: str, away: str) -> str | None:
    """Score Lisa — OVERRIDES puis EXTRA (grille site)."""
    key = match_key(home, away)
    if key in OVERRIDES:
        return OVERRIDES[key]
    for _date, h, a, score in EXTRA:
        if match_key(h, a) == key:
            return score
    return None


# Corrections manuelles (meilleur ratio MPP)
OVERRIDES: dict[str, str] = {
    "Afrique du Sud - Corée du Sud": "1-1",
    "Algérie - Autriche": "1-1",
    "Allemagne - Curaçao": "3-0",
    "Allemagne - Côte d'Ivoire": "2-1",
    "Angleterre - Croatie": "2-1",
    "Angleterre - Ghana": "2-0",
    "Argentine - Algérie": "2-0",
    "Argentine - Autriche": "2-0",
    "Australie - Turquie": "0-2",
    "Autriche - Jordanie": "2-0",
    "Belgique - Iran": "2-0",
    "Belgique - Égypte": "2-0",
    "Bosnie-Herzégovine - Qatar": "1-1",
    "Brésil - Maroc": "2-1",
    "Canada - Bosnie-Herzégovine": "2-0",
    "Canada - Qatar": "2-0",
    "Cap-Vert - Arabie saoudite": "1-1",
    "Colombie - Portugal": "0-1",
    "Colombie - RD Congo": "2-1",
    "Corée du Sud - Tchéquie": "1-1",
    "Croatie - Ghana": "1-1",
    "Curaçao - Côte d'Ivoire": "0-1",
    "Côte d'Ivoire - Équateur": "1-1",
    "Espagne - Cap-Vert": "2-0",
    "France - Irak": "3-0",
    "France - Sénégal": "2-0",
    "Ghana - Panama": "1-1",
    "Haïti - Écosse": "0-1",
    "Japon - Suède": "1-1",
    "Jordanie - Argentine": "0-1",
    "Maroc - Haïti": "1-0",
    "Mexique - Afrique du Sud": "2-0",
    "Mexique - Corée du Sud": "2-1",
    "Norvège - France": "0-1",
    "Nouvelle-Zélande - Belgique": "0-1",
    "Nouvelle-Zélande - Égypte": "0-2",
    "Panama - Angleterre": "0-1",
    "Panama - Croatie": "0-2",
    "Paraguay - Australie": "1-1",
    "Pays-Bas - Japon": "2-1",
    "Pays-Bas - Suède": "2-1",
    "Portugal - Ouzbékistan": "3-0",
    "Portugal - RD Congo": "2-0",
    "Qatar - Suisse": "0-1",
    "RD Congo - Ouzbékistan": "1-1",
    "Suisse - Bosnie-Herzégovine": "2-0",
    "Suisse - Canada": "1-1",
    "Suède - Tunisie": "2-1",
    "Sénégal - Irak": "1-0",
    "Tchéquie - Mexique": "1-1",
    "Tunisie - Pays-Bas": "0-1",
    "Turquie - États-Unis": "1-1",
    "Uruguay - Cap-Vert": "2-0",
    "Uruguay - Espagne": "0-1",
    "Écosse - Brésil": "0-1",
    "Écosse - Maroc": "0-2",
    "Égypte - Iran": "1-1",
    "Équateur - Allemagne": "0-1",
    "Équateur - Curaçao": "2-0",
    "États-Unis - Australie": "2-1",
    "États-Unis - Paraguay": "2-1",
}

# Matchs supplémentaires (captures récentes)
EXTRA = [
    ("15/06", "Côte d'Ivoire", "Équateur", "1-1"),
    ("15/06", "Suède", "Tunisie", "2-1"),
    ("15/06", "Espagne", "Cap-Vert", "2-0"),
    ("15/06", "Belgique", "Égypte", "2-0"),
    ("14/06", "Australie", "Turquie", "0-2"),
    ("14/06", "Allemagne", "Curaçao", "3-0"),
    ("14/06", "Pays-Bas", "Japon", "2-1"),
]


def main() -> None:
    out: list[dict] = []
    seen: set[str] = set()

    for m in MATCHES:
        r = analyze(m)
        key = r["match"]
        score = OVERRIDES.get(key, r["score"])
        out.append({
            "id": key.replace(" ", "_").replace("'", ""),
            "date": r["date"],
            "home": m.home,
            "away": m.away,
            "suggested": score,
            "probs": {"home": r["p1"], "draw": r["pN"], "away": r["p2"]},
        })
        seen.add(key)

    for date, home, away, score in EXTRA:
        key = f"{home} - {away}"
        if key not in seen:
            out.append({
                "id": key.replace(" ", "_"),
                "date": date,
                "home": home,
                "away": away,
                "suggested": score,
                "probs": {},
            })

    out.sort(key=lambda x: (x["date"].split("/")[1], x["date"].split("/")[0]))

    web_dir = Path(__file__).resolve().parents[1] / "web"
    web_dir.mkdir(exist_ok=True)
    path = web_dir / "matches.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {len(out)} matchs → {path}")


if __name__ == "__main__":
    main()
