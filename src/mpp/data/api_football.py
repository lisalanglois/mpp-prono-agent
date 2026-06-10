"""Client API-Football (api-football.com) — optionnel."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import requests


API_BASE = "https://v3.football.api-sports.io"


def _headers() -> dict[str, str]:
    key = os.environ.get("API_FOOTBALL_KEY", "")
    if not key:
        raise EnvironmentError(
            "API_FOOTBALL_KEY manquante. Définir dans .env ou l'environnement."
        )
    return {"x-apisports-key": key}


def fetch_fixtures(
    team_id: int | None = None,
    league_id: int | None = None,
    season: int | None = None,
    last: int = 10,
) -> pd.DataFrame:
    """
    Récupère les derniers matchs via API-Football.
    Docs : https://www.api-football.com/documentation-v3
    """
    params: dict[str, Any] = {"last": last}
    if team_id:
        params["team"] = team_id
    if league_id:
        params["league"] = league_id
    if season:
        params["season"] = season

    resp = requests.get(
        f"{API_BASE}/fixtures", headers=_headers(), params=params, timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for item in data.get("response", []):
        fix = item["fixture"]
        teams = item["teams"]
        goals = item["goals"]
        rows.append(
            {
                "date": fix["date"],
                "home_team": teams["home"]["name"],
                "away_team": teams["away"]["name"],
                "home_goals": goals["home"],
                "away_goals": goals["away"],
                "competition": str(item.get("league", {}).get("name", "")),
            }
        )
    return pd.DataFrame(rows)


def search_team_id(name: str) -> int | None:
    """Recherche l'ID équipe par nom."""
    resp = requests.get(
        f"{API_BASE}/teams",
        headers=_headers(),
        params={"search": name},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("response", [])
    if not results:
        return None
    return results[0]["team"]["id"]
