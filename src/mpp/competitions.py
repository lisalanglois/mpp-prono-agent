"""Calendrier multi-compétitions MPP (CDM, Euro…)."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
CONFIG = ROOT / "data" / "competitions.json"


def load_competitions_config() -> dict:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    return {"competitions": [], "site_base": ""}


def list_competitions() -> list[dict[str, Any]]:
    return load_competitions_config().get("competitions", [])


def parse_comp_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def get_competition(comp_id: str) -> dict[str, Any] | None:
    for c in list_competitions():
        if c["id"] == comp_id:
            return c
    return None


def get_active_competition(for_date: date | None = None) -> dict[str, Any] | None:
    """Compétition en cours (entre start et end inclus)."""
    today = for_date or date.today()
    for c in list_competitions():
        if parse_comp_date(c["start"]) <= today <= parse_comp_date(c["end"]):
            return c
    return None


def get_upcoming_pre_alert(for_date: date | None = None) -> list[dict[str, Any]]:
    """Compétitions dans la fenêtre J-7 … J-1 (email de préparation)."""
    today = for_date or date.today()
    out = []
    for c in list_competitions():
        days = (parse_comp_date(c["start"]) - today).days
        pre = c.get("pre_alert_days", 7)
        if 0 < days <= pre:
            c = dict(c)
            c["days_until_start"] = days
            out.append(c)
    return sorted(out, key=lambda x: x["days_until_start"])


def get_recently_ended(for_date: date | None = None, grace_days: int = 3) -> list[dict[str, Any]]:
    """Compétitions terminées depuis peu (email de clôture)."""
    today = for_date or date.today()
    out = []
    for c in list_competitions():
        end = parse_comp_date(c["end"])
        if end < today <= end + timedelta(days=grace_days):
            out.append(c)
    return out


def comp_urls(comp: dict[str, Any]) -> dict[str, str]:
    base = load_competitions_config().get("site_base", "").rstrip("/")
    pages = comp.get("pages", {})
    return {
        "grille": f"{base}{pages.get('grille', '/index.html')}",
        "tracker": f"{base}{pages.get('tracker', '/tracker.html')}",
        "mpp": "https://mpp.football",
    }


def load_grid(comp: dict[str, Any]) -> tuple[list[Any], dict[str, str]]:
    """Charge MATCHES + OVERRIDES pour une compétition."""
    module = comp.get("grid_module")
    overrides_mod = comp.get("overrides_module", "export_web")
    if not module:
        return [], {}

    grid = importlib.import_module(module)
    overrides = importlib.import_module(overrides_mod)
    matches = getattr(grid, "MATCHES", [])
    ov = getattr(overrides, "OVERRIDES", {})
    return matches, ov


def grid_to_rows(comp: dict[str, Any]) -> list[dict[str, str]]:
    """Liste {date, home, away, score, key} pour emails / export."""
    matches, overrides = load_grid(comp)
    if not matches:
        return []

    rows: list[dict[str, str]] = []
    analyze_fn = None
    grid_mod = comp.get("grid_module")
    if grid_mod:
        grid = importlib.import_module(grid_mod)
        analyze_fn = getattr(grid, "analyze", None)
        with_odds = getattr(grid, "_with_odds", lambda m: m)

    for m in matches:
        key = f"{m.home} - {m.away}"
        if key in overrides:
            score = overrides[key]
        elif analyze_fn:
            try:
                score = analyze_fn(with_odds(m))["score"]
            except Exception:
                score = "1-1"
        else:
            score = "1-1"
        h, a = score.split("-", 1)
        rows.append({
            "date": m.date,
            "home": m.home,
            "away": m.away,
            "key": key,
            "score": score,
            "score_home": h.strip(),
            "score_away": a.strip(),
        })

    return sorted(rows, key=lambda r: tuple(map(int, r["date"].split("/")[::-1])))
