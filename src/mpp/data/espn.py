"""Récupération fixtures CDM 2026 + cotes via ESPN (gratuit, sans clé)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import requests

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"


def american_to_decimal(american: int | float) -> float:
    """Convertit une cote américaine en cote décimale."""
    a = int(american)
    if a > 0:
        return 1 + a / 100
    return 1 + 100 / abs(a)


def fetch_scoreboard(for_date: date | None = None) -> dict[str, Any]:
    """Scoreboard FIFA World Cup pour une date (défaut : aujourd'hui)."""
    params: dict[str, str] = {}
    if for_date:
        params["dates"] = for_date.strftime("%Y%m%d")
    resp = requests.get(ESPN_SCOREBOARD, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_upcoming_days(days: int = 3) -> list[dict[str, Any]]:
    """Matchs à venir sur N jours (scoreboard ESPN jour par jour)."""
    matches: list[dict[str, Any]] = []
    today = date.today()
    seen: set[str] = set()

    for offset in range(days):
        d = today + timedelta(days=offset)
        data = fetch_scoreboard(d)
        for event in data.get("events", []):
            eid = event.get("id", "")
            if eid in seen:
                continue
            seen.add(eid)
            parsed = parse_event(event)
            if parsed:
                matches.append(parsed)

    return sorted(matches, key=lambda m: m["kickoff"])


def parse_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Extrait home, away, cotes, forme depuis un event ESPN."""
    comp = event.get("competitions", [{}])[0]
    competitors = comp.get("competitors", [])
    if len(competitors) != 2:
        return None

    home = next(c for c in competitors if c.get("homeAway") == "home")
    away = next(c for c in competitors if c.get("homeAway") == "away")

    odds_block = (comp.get("odds") or [{}])[0]
    ml = odds_block.get("moneyline", {})

    odds: dict[str, float] | None = None
    if ml:
        try:
            odds = {
                "home": american_to_decimal(ml["home"]["close"]["odds"]),
                "draw": american_to_decimal(ml["draw"]["close"]["odds"]),
                "away": american_to_decimal(ml["away"]["close"]["odds"]),
            }
        except (KeyError, TypeError, ValueError):
            odds = None

    over_under = odds_block.get("overUnder")

    return {
        "event_id": event.get("id"),
        "kickoff": event.get("date", ""),
        "home": home["team"]["displayName"],
        "away": away["team"]["displayName"],
        "home_form": home.get("form", ""),
        "away_form": away.get("form", ""),
        "venue": comp.get("venue", {}).get("fullName", ""),
        "status": comp.get("status", {}).get("type", {}).get("description", ""),
        "odds": odds,
        "over_under": over_under,
        "competition": "World Cup 2026",
    }


def form_string_to_points(form: str, n: int = 5) -> float:
    """Convertit WWWDD en score forme 0–3 par match."""
    if not form:
        return 1.5
    mapping = {"W": 3.0, "D": 1.0, "L": 0.0}
    chars = form[:n]
    return sum(mapping.get(c, 1.0) for c in chars) / len(chars)


def fixtures_dataframe(days: int = 3) -> pd.DataFrame:
    """DataFrame des prochains matchs avec cotes."""
    rows = fetch_upcoming_days(days)
    return pd.DataFrame(rows)
