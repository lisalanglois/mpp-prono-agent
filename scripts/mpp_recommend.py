"""Score MPP — stratégie V3 (CDM 2026).

1/N/2 : foule MPP → cotes ESPN → Klement.
Score exact : Poisson + différenciation MPP (éviter 1-0 / 0-1 banals si alternative viable).
"""

from __future__ import annotations

import json
from pathlib import Path

from export_web import get_user_score, match_key
from mpp_grille_cdm import MATCHES, _with_odds, fit_lambdas_from_decimal
from mpp.models.poisson import MPP_CROWD_SCORES, score_matrix, top_exact_scores
from mpp.mpp_strategy import pick_mpp_score

ROOT = Path(__file__).resolve().parents[1]
KLEMENT_PATH = ROOT / "data" / "klement_predictions.json"

CROWD_STRONG = 55
CROWD_CLEAR = 50
CROWD_DRAW_MIN = 40
CROWD_DRAW_BALANCED = 38
KLEMENT_TIEBREAK = 10
KLEMENT_STRONG = 15


def _outcome(score: str) -> str:
    h, a = map(int, score.split("-"))
    if h > a:
        return "home"
    if h < a:
        return "away"
    return "draw"


def _get_match(home: str, away: str):
    return next((x for x in MATCHES if x.home == home and x.away == away), None)


def load_klement() -> dict:
    if KLEMENT_PATH.exists():
        return json.loads(KLEMENT_PATH.read_text(encoding="utf-8"))
    return {}


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


def klement_diff(home: str, away: str, klement: dict) -> int:
    strength = klement.get("team_strength", {})
    return strength.get(home, 40) - strength.get(away, 40)


def _crowd_favorite(m) -> tuple[str, float]:
    if m.crowd_home >= m.crowd_draw and m.crowd_home >= m.crowd_away:
        return "home", m.crowd_home
    if m.crowd_away >= m.crowd_draw:
        return "away", m.crowd_away
    return "draw", m.crowd_draw


def _odds_implied(m) -> dict[str, float] | None:
    if not m.odds_home:
        return None
    ih, id_, ia = 1 / m.odds_home, 1 / m.odds_draw, 1 / m.odds_away
    t = ih + id_ + ia
    return {"home": ih / t, "draw": id_ / t, "away": ia / t}


def _odds_favorite(m) -> tuple[str, float] | None:
    imp = _odds_implied(m)
    if not imp:
        return None
    best = max(imp, key=imp.get)
    return best, imp[best] * 100


def _blend_and_matrix(home: str, away: str):
    m = _get_match(home, away)
    if not m:
        return None, {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}, []
    m = _with_odds(m)
    if m.odds_home:
        lh, la, blend = fit_lambdas_from_decimal(m.odds_home, m.odds_draw, m.odds_away)
    else:
        ch = max(m.crowd_home, 8) / 100
        cd = max(m.crowd_draw, 8) / 100
        ca = max(m.crowd_away, 8) / 100
        lh, la, blend = fit_lambdas_from_decimal(1 / ch, 1 / cd, 1 / ca)
    mat = score_matrix(lh, la)
    top = top_exact_scores(mat, 12)
    return m, blend, top


def _matrix_and_top(m):
    m2, _, top = _blend_and_matrix(m.home, m.away)
    return m2, top


def _draw_allowed(m, k_o: str | None, k_diff: int) -> bool:
    """Nul seulement si la foule (ou cotes) le soutient vraiment."""
    cf, cp = _crowd_favorite(m)
    spread = abs(m.crowd_home - m.crowd_away)
    if cp >= CROWD_STRONG and cf != "draw":
        return False
    if m.crowd_draw >= CROWD_DRAW_MIN and max(m.crowd_home, m.crowd_away) < CROWD_CLEAR:
        return True
    if m.crowd_draw >= 45:
        return True
    if (
        m.crowd_draw >= CROWD_DRAW_BALANCED
        and spread <= 12
        and max(m.crowd_home, m.crowd_away) < CROWD_STRONG
    ):
        return True
    imp = _odds_implied(m)
    if imp and imp["draw"] >= 0.30 and max(imp["home"], imp["away"]) < 0.48:
        return True
    if k_o == "draw" and abs(k_diff) < 8 and m.crowd_draw >= 35:
        return True
    return False


def _target_outcome_v3(m, key: str, klement: dict) -> tuple[str, str]:
    """Retourne (outcome, raison courte)."""
    k_o = klement_outcome(key, m.home, m.away, klement)
    k_diff = klement_diff(m.home, m.away, klement)
    cf, cp = _crowd_favorite(m)
    odds_f = _odds_favorite(m)

    if _draw_allowed(m, k_o, k_diff):
        return "draw", f"foule nul {m.crowd_draw:.0f}%"

    # Favori foule clair
    if cp >= CROWD_STRONG and cf != "draw":
        return cf, f"foule {cp:.0f}%"

    # Cotes bookmaker claires
    if odds_f:
        of, op = odds_f
        if op >= 58 and of != "draw":
            if cf == of or cp < CROWD_STRONG:
                return of, f"cotes {op:.0f}%"

    # Foule modérée (≥ 50 %) — prioritaire sur Klement pour MPP
    if cp >= CROWD_CLEAR and cf != "draw":
        return cf, f"foule {cp:.0f}%"

    # Match serré — Klement puis cotes
    if abs(k_diff) >= KLEMENT_TIEBREAK and k_o != "draw":
        return k_o, f"Klement Δ{k_diff:+d}"

    if odds_f and odds_f[1] >= 52:
        return odds_f[0], f"cotes {odds_f[1]:.0f}%"

    if cf != "draw":
        return cf, f"foule {cp:.0f}%"

    return k_o or "draw", "défaut"


def _confidence(m, target: str, reason: str) -> str:
    cf, cp = _crowd_favorite(m)
    k_diff = klement_diff(m.home, m.away, load_klement())
    odds_f = _odds_favorite(m)

    if target == "draw":
        if m.crowd_draw >= 42 and max(m.crowd_home, m.crowd_away) < 48:
            return "high"
        if m.crowd_draw >= 38:
            return "medium"
        return "low"

    if cp >= 65 and cf == target:
        return "high"
    if cp >= CROWD_STRONG and cf == target:
        return "high"
    if odds_f and odds_f[0] == target and odds_f[1] >= 60:
        return "high"
    if cp >= CROWD_CLEAR and cf == target:
        return "medium"
    if "Klement" in reason and abs(k_diff) >= KLEMENT_STRONG:
        return "medium"
    if odds_f and odds_f[0] == target:
        return "medium"
    return "low"


def _best_exact_for_outcome(
    top: list[tuple[str, float]],
    target: str,
    m,
    confidence: str,
    blend: dict[str, float],
) -> tuple[str, str]:
    """Score exact MPP : bon 1/N/2 + différenciation vs grilles banals."""
    candidates = [(s, p) for s, p in top if _outcome(s) == target]
    if not candidates:
        fallback = {
            "home": "2-0",
            "away": "0-2",
            "draw": "1-1" if m.crowd_draw >= 35 else "0-0",
        }
        return fallback[target], "défaut MPP"

    cf, cp = _crowd_favorite(m)
    stat_s, stat_p = candidates[0]
    conf_label = {"high": "élevé", "medium": "modéré", "low": "faible"}.get(confidence, "modéré")

    # Gros favori (≥ 78 %) → viser 2-0 / 3-0 / 0-2 (tes exacts J1-J2 : 2-0, 3-0, 2-1)
    if cp >= 78 and cf == target:
        prefs = (
            ("3-0", "2-0", "3-1", "2-1", "4-0")
            if target == "home"
            else ("0-3", "0-2", "1-3", "1-2", "0-4")
        )
        for score in prefs:
            for s, p in candidates:
                if s == score and p >= stat_p * 0.40:
                    if s not in MPP_CROWD_SCORES or score in ("3-0", "0-3", "3-1", "1-3"):
                        return s, f"favori {cp:.0f}% · diff MPP"
        for s, p in candidates:
            if s not in MPP_CROWD_SCORES and p >= stat_p * 0.45:
                return s, f"favori {cp:.0f}% · rare"

    # Favori modéré (55–77 %) → 2-0 / 2-1 / 0-2 plutôt que 1-0 / 0-1
    if cp >= CROWD_STRONG and cf == target:
        prefs = (
            ("2-0", "2-1", "3-0", "3-1")
            if target == "home"
            else ("0-2", "1-2", "0-3", "1-3")
        )
        for score in prefs:
            for s, p in candidates:
                if s == score and p >= stat_p * 0.50:
                    return s, f"favori {cp:.0f}% · diff vs 1-0"

    # Nul → différencier 0-0 / 2-2 si 1-1 trop banal
    if target == "draw":
        if m.crowd_draw >= 40:
            for score in ("1-1", "0-0", "2-2"):
                for s, p in candidates:
                    if s == score and p >= stat_p * 0.45:
                        note = "nul foule" if score == "1-1" else "nul différencié"
                        return s, note
        score, prob, note = pick_mpp_score(candidates, conf_label, blend)
        return score, note

    # Stratégie MPP standard sur candidats filtrés (même 1/N/2)
    score, prob, note = pick_mpp_score(candidates, conf_label, blend)
    if score in MPP_CROWD_SCORES and stat_s not in MPP_CROWD_SCORES:
        return stat_s, "stat max (moins risqué)"
    return score, note


def recommend_mpp_score(home: str, away: str, klement: dict) -> dict:
    """Score recommandé pour mpp.football (stratégie V3)."""
    key = match_key(home, away)
    user_score = get_user_score(home, away)
    m = _get_match(home, away)

    if m is None:
        score = user_score or "1-1"
        h, a = score.split("-")
        return _result(key, home, away, user_score, score, h, a, "low", "grille", "—", "draw", None)

    m2, top = _matrix_and_top(m)
    _, blend, _ = _blend_and_matrix(home, away)
    target, reason = _target_outcome_v3(m2, key, klement)
    conf = _confidence(m2, target, reason)
    rec, exact_note = _best_exact_for_outcome(top, target, m2, conf, blend)

    user_o = _outcome(user_score) if user_score else None
    changed = user_score is not None and user_score != rec
    needs_action = user_score is None or changed

    source = "v3"
    if user_score == rec:
        source = "ok"

    h, a = rec.split("-")
    return _result(
        key, home, away, user_score, rec, h, a, conf, source, reason, target,
        klement_outcome(key, home, away, klement),
        changed=changed,
        needs_action=needs_action,
        crowd=f"{m.crowd_home:.0f}/{m.crowd_draw:.0f}/{m.crowd_away:.0f}",
        has_odds=bool(m2.odds_home),
        exact_note=exact_note,
    )


def _result(
    key, home, away, user_score, rec, h, a, conf, source, reason, target, k_o,
    *, changed=False, needs_action=False, crowd="", has_odds=False, exact_note="",
) -> dict:
    return {
        "key": key,
        "home": home,
        "away": away,
        "user_score": user_score,
        "recommended_score": rec,
        "score_home": h.strip(),
        "score_away": a.strip(),
        "confidence": conf,
        "source": source,
        "reason": reason,
        "exact_note": exact_note,
        "target_outcome": target,
        "klement_outcome": k_o,
        "changed": changed,
        "needs_action": needs_action,
        "crowd": crowd,
        "has_odds": has_odds,
        "mpp_instruction": f"mpp.football → {home} vs {away} → {h.strip()} - {a.strip()}",
    }


def recommend_all_unplayed(played_keys: set[str]) -> list[dict]:
    klement = load_klement()
    out = []
    for m in MATCHES:
        key = match_key(m.home, m.away)
        if key in played_keys:
            continue
        out.append(recommend_mpp_score(m.home, m.away, klement))
    return out
