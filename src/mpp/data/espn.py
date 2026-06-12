"""Récupération fixtures CDM 2026 + cotes via ESPN (gratuit, sans clé)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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

    odds_block = (comp.get("odds") or [{}])[0] or {}
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

    status_type = comp.get("status", {}).get("type", {})
    status_short = (
        status_type.get("detail")
        or status_type.get("shortDetail")
        or status_type.get("name", "")
    )
    status_name = status_type.get("name", "")
    status_state = status_type.get("state", "")
    status_completed = bool(status_type.get("completed", False))

    # Normalise ESPN (STATUS_FULL_TIME → FT, etc.)
    _norm = {
        "STATUS_FULL_TIME": "FT",
        "STATUS_FINAL": "FT",
        "STATUS_FINAL_AET": "AET",
        "STATUS_FINAL_PEN": "PEN",
        "STATUS_FULL_TIME_PEN": "PEN",
    }
    status_short = _norm.get(status_name, status_short)

    home_score = home.get("score")
    away_score = away.get("score")
    if isinstance(home_score, dict):
        home_goals = home_score.get("value")
    else:
        home_goals = home_score
    if isinstance(away_score, dict):
        away_goals = away_score.get("value")
    else:
        away_goals = away_score

    def _to_int(v: Any) -> int | None:
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    home_goals = _to_int(home_goals)
    away_goals = _to_int(away_goals)

    return {
        "event_id": event.get("id"),
        "kickoff": event.get("date", ""),
        "home": home["team"]["displayName"],
        "away": away["team"]["displayName"],
        "home_form": home.get("form", ""),
        "away_form": away.get("form", ""),
        "venue": comp.get("venue", {}).get("fullName", ""),
        "status": status_type.get("description", ""),
        "status_short": status_short,
        "status_name": status_name,
        "status_state": status_state,
        "status_completed": status_completed,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "odds": odds,
        "over_under": over_under,
        "competition": "World Cup 2026",
    }


def fetch_scoreboard_range(start: date, end: date) -> list[dict[str, Any]]:
    """Tous les matchs CDM entre deux dates (inclus)."""
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    d = start
    while d <= end:
        data = fetch_scoreboard(d)
        for event in data.get("events", []):
            eid = event.get("id", "")
            if eid in seen:
                continue
            seen.add(eid)
            parsed = parse_event(event)
            if parsed:
                matches.append(parsed)
        d += timedelta(days=1)
    return sorted(matches, key=lambda m: m["kickoff"])


def fetch_upcoming_within(hours: int = 48) -> list[dict[str, Any]]:
    """Matchs CDM pas encore joués dont le coup d'envoi est dans les N prochaines heures."""
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=hours)
    end_date = deadline.date()
    start_date = now.date()

    upcoming: list[dict[str, Any]] = []
    seen: set[str] = set()

    d = start_date
    while d <= end_date:
        data = fetch_scoreboard(d)
        for event in data.get("events", []):
            eid = event.get("id", "")
            if eid in seen:
                continue
            seen.add(eid)
            parsed = parse_event(event)
            if not parsed or is_match_finished(parsed):
                continue
            if parsed.get("status_state") == "post":
                continue
            kickoff_raw = parsed.get("kickoff")
            if not kickoff_raw:
                continue
            kickoff = datetime.fromisoformat(kickoff_raw.replace("Z", "+00:00"))
            if kickoff < now or kickoff > deadline:
                continue
            parsed["kickoff_dt"] = kickoff.isoformat()
            parsed["hours_until"] = round((kickoff - now).total_seconds() / 3600, 1)
            upcoming.append(parsed)
        d += timedelta(days=1)

    return sorted(upcoming, key=lambda m: m.get("kickoff", ""))


def is_match_finished(m: dict[str, Any]) -> bool:
    """True si le match est terminé (pas un 0-0 planifié)."""
    if m.get("home_goals") is None or m.get("away_goals") is None:
        return False
    if m.get("status_completed") or m.get("status_state") == "post":
        return "SCHEDULED" not in str(m.get("status_name", "")).upper()
    short = str(m.get("status_short", "")).upper()
    if short in ("FT", "AET", "PEN"):
        return True
    if "FULL_TIME" in short or "FINAL" in short:
        return True
    desc = str(m.get("status", "")).lower()
    return "full time" in desc or desc == "final"


def fetch_finished_since(wc_start: date | None = None) -> list[dict[str, Any]]:
    """Matchs terminés depuis le début de la CDM."""
    start = wc_start or date(2026, 6, 11)
    end = date.today()
    finished = []
    for m in fetch_scoreboard_range(start, end):
        if is_match_finished(m):
            finished.append(m)
    return finished


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
