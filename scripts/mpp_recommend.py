"""Score MPP unique à recopier — fusion grille Lisa + direction Klement si diverge."""

from __future__ import annotations

from export_web import OVERRIDES
from mpp_grille_cdm import MATCHES, _with_odds, analyze
from mpp.models.poisson import score_matrix, top_exact_scores


def _outcome(score: str) -> str:
    h, a = map(int, score.split("-"))
    if h > a:
        return "home"
    if h < a:
        return "away"
    return "draw"


def _direction_label(outcome: str | None, home: str, away: str) -> str:
    if outcome == "home":
        return f"victoire {home}"
    if outcome == "away":
        return f"victoire {away}"
    if outcome == "draw":
        return "match nul"
    return "—"


def _get_match(home: str, away: str):
    return next((x for x in MATCHES if x.home == home and x.away == away), None)


def _model_score(home: str, away: str) -> str:
    m = _get_match(home, away)
    if not m:
        return "1-1"
    return analyze(_with_odds(m))["score"]


def _score_for_outcome(home: str, away: str, outcome: str, klement: dict) -> str:
    """Meilleur score exact compatible avec la direction Klement."""
    m = _get_match(home, away)
    if m:
        m = _with_odds(m)
        if m.odds_home:
            from mpp_grille_cdm import fit_lambdas_from_decimal
            lh, la, _ = fit_lambdas_from_decimal(m.odds_home, m.odds_draw, m.odds_away)
        else:
            from mpp_grille_cdm import fit_lambdas_from_decimal, mpp_probs
            probs = mpp_probs(m.pts_home, m.pts_draw, m.pts_away)
            lh, la, _ = fit_lambdas_from_decimal(
                200 / m.pts_home, 200 / m.pts_draw, 200 / m.pts_away
            )
        top = top_exact_scores(score_matrix(lh, la), 15)
        for score, _ in top:
            if _outcome(score) == outcome:
                return score

    strength = klement.get("team_strength", {})
    diff = strength.get(home, 40) - strength.get(away, 40)
    if outcome == "draw":
        return "1-1"
    if outcome == "home":
        return "2-0" if diff >= 15 else "2-1"
    return "0-2" if diff <= -15 else "1-2"


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


def recommend_mpp_score(home: str, away: str, klement: dict) -> dict:
    """
    Un seul score à mettre sur mpp.football.
    Klement corrige surtout quand ta grille dit nul mais Klement voit un favori.
    """
    key = f"{home} - {away}"
    user_score = OVERRIDES.get(key) or _model_score(home, away)
    user_o = _outcome(user_score)
    k_o = klement_outcome(key, home, away, klement)

    use_klement = False
    if k_o and user_o != k_o:
        if user_o == "draw" and k_o != "draw":
            # ex. Corée 1-1 → Klement victoire Corée
            use_klement = True
        elif user_o != "draw" and k_o != "draw" and user_o != k_o:
            # directions opposées → Klement
            use_klement = True
        # sinon : tu as un favori, Klement dit nul → on garde ta grille (ex. Canada 2-0)

    if use_klement and k_o:
        rec = _score_for_outcome(home, away, k_o, klement)
        h, a = rec.split("-")
        return {
            "key": key,
            "home": home,
            "away": away,
            "user_score": user_score,
            "recommended_score": rec,
            "score_home": h,
            "score_away": a,
            "source": "klement",
            "klement_override": True,
            "reason": (
                f"Klement voit {_direction_label(k_o, home, away)} "
                f"(ta grille : {_direction_label(user_o, home, away)} {user_score}) "
                f"→ mets {rec}"
            ),
            "mpp_instruction": f"mpp.football → {home} vs {away} → mets {h} - {a}",
        }

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
        "klement_override": False,
        "reason": f"→ mets {user_score} (recopie tel quel)",
        "mpp_instruction": f"mpp.football → {home} vs {away} → mets {h.strip()} - {a.strip()}",
    }
