"""Score MPP — stratégie V2 (CDM 2026).

Apprentissage J1–J2 : plus de nuls, moins de 2-0 automatiques, 1/N/2 ancré sur le modèle Poisson.
"""

from __future__ import annotations

import json
from pathlib import Path

from export_web import get_user_score, match_key
from mpp_grille_cdm import MATCHES, _with_odds, analyze, fit_lambdas_from_decimal, mpp_probs
from mpp.models.poisson import MPP_CROWD_SCORES, outcome_probabilities, score_matrix, top_exact_scores

ROOT = Path(__file__).resolve().parents[1]
KLEMENT_PATH = ROOT / "data" / "klement_predictions.json"

# Taux de nuls observé J1–J2 CDM 2026 ≈ 29 % (vs ~25 % historique)
CDM_DRAW_BOOST = 1.15
DRAW_THRESHOLD = 0.27
DRAW_THRESHOLD_STRONG = 0.30
FAVORITE_ODDS = 1.45
FAVORITE_CROWD = 75
KLEMENT_TIEBREAK_DIFF = 18


def _outcome(score: str) -> str:
    h, a = map(int, score.split("-"))
    if h > a:
        return "home"
    if h < a:
        return "away"
    return "draw"


def _get_match(home: str, away: str):
    return next((x for x in MATCHES if x.home == home and x.away == away), None)


def _model_score(home: str, away: str) -> str:
    m = _get_match(home, away)
    if not m:
        return "1-1"
    return analyze(_with_odds(m))["score"]


def _blend_and_matrix(home: str, away: str):
    m = _get_match(home, away)
    if not m:
        return None, {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}, []
    m = _with_odds(m)
    if m.odds_home:
        lh, la, blend = fit_lambdas_from_decimal(m.odds_home, m.odds_draw, m.odds_away)
    else:
        blend = mpp_probs(m.pts_home, m.pts_draw, m.pts_away)
        lh, la, _ = fit_lambdas_from_decimal(
            200 / m.pts_home, 200 / m.pts_draw, 200 / m.pts_away
        )
    mat = score_matrix(lh, la)
    op = outcome_probabilities(mat)
    if op["draw"] >= 0.24:
        boosted = op["draw"] * CDM_DRAW_BOOST
        total = op["home"] + boosted + op["away"]
        blend_adj = {
            "home": op["home"] / total,
            "draw": boosted / total,
            "away": op["away"] / total,
        }
    else:
        blend_adj = dict(op)
    top = top_exact_scores(mat, 12)
    return m, blend_adj, top


def _classify_tier(m, blend: dict) -> str:
    if m.odds_home and min(m.odds_home, m.odds_away) < FAVORITE_ODDS:
        return "A"
    fav_pct = max(m.crowd_home, m.crowd_draw, m.crowd_away)
    if fav_pct >= FAVORITE_CROWD:
        return "A"
    if blend["draw"] >= DRAW_THRESHOLD or m.crowd_draw >= 38:
        return "B"
    return "C"


def klement_outcome(key: str, home: str, away: str, klement: dict) -> str | None:
    explicit = klement.get("explicit_outcomes", {})
    if key in explicit:
        return explicit[key]
    strength = klement.get("team_strength", {})
    hs, as_ = strength.get(home, 40), strength.get(away, 40)
    diff = hs - as_
    if abs(diff) < 8:
        return "draw"
    return "home" if diff > 0 else "away"


def _favorite_outcome(m) -> str:
    if m.crowd_home >= m.crowd_draw and m.crowd_home >= m.crowd_away:
        return "home"
    if m.crowd_away >= m.crowd_draw:
        return "away"
    return "draw"


def _target_outcome_v2(
    home: str,
    away: str,
    key: str,
    klement: dict,
    m,
    blend: dict,
    tier: str,
) -> str:
    mod_o = _outcome(_model_score(home, away))
    k_o = klement_outcome(key, home, away, klement)
    strength = klement.get("team_strength", {})
    diff = strength.get(home, 40) - strength.get(away, 40)

    if tier == "B":
        if blend["draw"] >= DRAW_THRESHOLD_STRONG or m.crowd_draw >= 40:
            return "draw"
        if k_o == "draw":
            return "draw"
        return mod_o

    if tier == "A":
        fav = _favorite_outcome(m)
        if fav != "draw":
            return fav
        if m.odds_home and m.odds_home <= m.odds_away:
            return "home"
        return "away"

    # Tier C — modèle, Klement en tie-break fort
    if mod_o == "draw" and k_o and k_o != "draw" and abs(diff) >= KLEMENT_TIEBREAK_DIFF:
        return k_o
    if mod_o != "draw" and k_o == "draw" and blend["draw"] >= DRAW_THRESHOLD:
        return "draw"
    return mod_o


def _best_exact_for_outcome(
    top: list[tuple[str, float]],
    target: str,
    tier: str,
    m,
) -> str:
    candidates = [(s, p) for s, p in top if _outcome(s) == target]
    if not candidates:
        defaults = {"home": "1-0", "away": "0-1", "draw": "1-1"}
        return defaults[target]

    if tier == "A" and target in ("home", "away"):
        for pref in ("1-0", "2-0", "2-1", "3-0"):
            for s, _ in candidates:
                if s == pref:
                    return s
        return candidates[0][0]

    if tier == "B" and target == "draw":
        for pref in ("1-1", "0-0", "2-2"):
            for s, _ in candidates:
                if s == pref:
                    return s
        return candidates[0][0]

    # Différenciation MPP : préférer score non-banal si proba proche
    best_s, best_p = candidates[0]
    for s, p in candidates[1:5]:
        if s not in MPP_CROWD_SCORES and p >= best_p * 0.55:
            return s
    return best_s


def recommend_mpp_score(home: str, away: str, klement: dict) -> dict:
    """Un seul score à mettre sur mpp.football (stratégie V2)."""
    key = match_key(home, away)
    user_score = get_user_score(home, away) or _model_score(home, away)
    m, blend, top = _blend_and_matrix(home, away)

    if m is None:
        h, a = user_score.split("-")
        return {
            "key": key,
            "home": home,
            "away": away,
            "user_score": user_score,
            "recommended_score": user_score,
            "score_home": h.strip(),
            "score_away": a.strip(),
            "source": "grille",
            "tier": "C",
            "klement_override": False,
            "changed": False,
            "mpp_instruction": f"mpp.football → {home} vs {away} → {h.strip()} - {a.strip()}",
        }

    tier = _classify_tier(m, blend)
    target_o = _target_outcome_v2(home, away, key, klement, m, blend, tier)
    rec = _best_exact_for_outcome(top, target_o, tier, m)

    user_o = _outcome(user_score)
    changed = user_score != rec
    source = "v2"
    if user_o == target_o and user_score == rec:
        source = "grille"
    elif user_o == target_o:
        source = "v2-exact"

    h, a = rec.split("-")
    return {
        "key": key,
        "home": home,
        "away": away,
        "user_score": user_score,
        "recommended_score": rec,
        "score_home": h.strip(),
        "score_away": a.strip(),
        "source": source,
        "tier": tier,
        "target_outcome": target_o,
        "p_draw": round(blend["draw"], 3),
        "klement_outcome": klement_outcome(key, home, away, klement),
        "klement_override": user_o != target_o and klement_outcome(key, home, away, klement) == target_o,
        "changed": changed,
        "mpp_instruction": f"mpp.football → {home} vs {away} → {h.strip()} - {a.strip()}",
    }


def load_klement() -> dict:
    if KLEMENT_PATH.exists():
        return json.loads(KLEMENT_PATH.read_text(encoding="utf-8"))
    return {}


def recommend_all_unplayed(played_keys: set[str]) -> list[dict]:
    klement = load_klement()
    out = []
    for m in MATCHES:
        key = match_key(m.home, m.away)
        if key in played_keys:
            continue
        out.append(recommend_mpp_score(m.home, m.away, klement))
    return out
