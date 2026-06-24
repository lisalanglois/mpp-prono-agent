#!/usr/bin/env python3
"""Batch MPP — pronostics exacts pour tous les matchs CDM 2026."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mpp.models.poisson import (
    MPP_CROWD_SCORES,
    outcome_probabilities,
    score_matrix,
    top_exact_scores,
)


@dataclass
class MppMatch:
    date: str
    home: str
    away: str
    pts_home: int
    pts_draw: int
    pts_away: int
    crowd_home: float
    crowd_draw: float
    crowd_away: float
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None


def mpp_probs(h: int, d: int, a: int) -> dict[str, float]:
    """Probabilités implicites depuis les points MPP (inverse des points)."""
    ih, id_, ia = 1 / h, 1 / d, 1 / a
    t = ih + id_ + ia
    return {"home": ih / t, "draw": id_ / t, "away": ia / t}


def fit_lambdas_from_decimal(
    odds_home: float, odds_draw: float, odds_away: float
) -> tuple[float, float, dict[str, float]]:
    """λ calibrés depuis cotes décimales ESPN."""
    ih, id_, ia = 1 / odds_home, 1 / odds_draw, 1 / odds_away
    t = ih + id_ + ia
    p = {"home": ih / t, "draw": id_ / t, "away": ia / t}
    total = 2.35
    if p["home"] > 0.62:
        lh = 0.5 + total * p["home"] * 0.82
        la = max(0.22, total - lh + 0.12)
    elif p["away"] > 0.62:
        la = 0.5 + total * p["away"] * 0.82
        lh = max(0.22, total - la + 0.12)
    elif p["draw"] > 0.30:
        lh, la = 1.05, 1.05
    else:
        lh = 1.1 + (p["home"] - p["away"]) * 1.4
        la = 1.1 + (p["away"] - p["home"]) * 1.4
    if max(p["home"], p["away"]) > 0.78:
        under = max(0.2, min(lh, la) - 0.15)
        if p["home"] > p["away"]:
            la = min(la, under)
        else:
            lh = min(lh, under)
    return max(0.2, round(lh, 2)), max(0.2, round(la, 2)), p


def pick_mpp_score_v2(
    top: list[tuple[str, float]],
    p_home: float,
    p_draw: float,
    p_away: float,
    crowd_home: float,
    crowd_draw: float,
    crowd_away: float,
) -> tuple[str, str]:
    """
    Choisit score MPP optimal.
    Returns: (score_conseillé, note_courte)
    """
    if not top:
        return "1-1", "défaut"

    stat, sp = top[0]
    # Favori = communauté MPP (plus fiable que le modèle seul)
    if crowd_home >= crowd_draw and crowd_home >= crowd_away:
        fav, fav_pct = "home", crowd_home
    elif crowd_away >= crowd_draw:
        fav, fav_pct = "away", crowd_away
    else:
        fav, fav_pct = "draw", crowd_draw

    def parse(s: str) -> tuple[int, int]:
        a, b = s.split("-")
        return int(a), int(b)

    def outcome(s: str) -> str:
        h, a = parse(s)
        if h > a:
            return "home"
        if h < a:
            return "away"
        return "draw"

    # Gros favori (>75%) → score DOIT aller dans le sens du favori
    if fav_pct >= 75 and fav != "draw":
        candidates = [
            (s, p) for s, p in top[:12]
            if outcome(s) == fav and p >= sp * 0.30
        ]
        # Prioriser non-banal
        for score, prob in candidates:
            if score not in MPP_CROWD_SCORES:
                return score, f"diff vs foule ({fav_pct:.0f}%)"
        if candidates:
            return candidates[0][0], f"favori ({fav_pct:.0f}%)"

    # Match serré / nul probable — CDM 2026 : taux nuls ~29 % (boost vs historique)
    if p_draw > 0.26 or crowd_draw > 35:
        for score in ("1-1", "0-0", "2-2"):
            for s, p in top[:10]:
                if s == score and p >= sp * 0.50:
                    if score != stat or crowd_draw > 40:
                        return score, "profil nul CDM"

    # Favori modéré → différencier si 2e score proche
    for score, prob in top[1:6]:
        if score in MPP_CROWD_SCORES and fav_pct < 75:
            continue
        if outcome(score) == fav and prob >= sp * 0.58:
            if score not in MPP_CROWD_SCORES or fav_pct >= 70:
                return score, "alt proche"

    # Value outsider uniquement si proba modèle >28% ET communauté <12%
    if crowd_away < 12 and p_away > 0.28 and fav == "home" and p_home < 0.55:
        for score, prob in top[:8]:
            h, a = parse(score)
            if a > h and prob >= sp * 0.25:
                return score, "value outsider"

    return stat, "stat max"


# Cotes ESPN décimales (juin 2026, live)
ESPN_ODDS: dict[tuple[str, str], tuple[float, float, float]] = {
    ("Mexique", "Afrique du Sud"): (1.41, 4.60, 8.50),
    ("Corée du Sud", "Tchéquie"): (2.65, 3.15, 2.90),
    ("Canada", "Bosnie-Herzégovine"): (1.80, 3.70, 4.60),
    ("États-Unis", "Paraguay"): (1.95, 3.45, 3.95),
    ("Qatar", "Suisse"): (12.0, 6.50, 1.24),
    ("Brésil", "Maroc"): (1.69, 3.75, 5.50),
    ("Haïti", "Écosse"): (6.00, 4.30, 1.56),
    ("France", "Sénégal"): (1.47, 4.50, 7.00),
    ("Irak", "Norvège"): (14.0, 7.00, 1.21),
    ("Argentine", "Algérie"): (1.41, 4.60, 9.00),
    ("Autriche", "Jordanie"): (1.32, 5.50, 9.50),
    ("Portugal", "RD Congo"): (1.29, 5.75, 11.0),
    ("Angleterre", "Croatie"): (1.71, 3.85, 4.80),
    ("Ghana", "Panama"): (2.10, 3.45, 3.65),
    ("Ouzbékistan", "Colombie"): (8.50, 4.60, 1.42),
    ("Tchéquie", "Afrique du Sud"): (1.95, 3.40, 4.20),
    ("Suisse", "Bosnie-Herzégovine"): (1.62, 4.10, 5.50),
    ("Canada", "Qatar"): (1.31, 5.25, 10.5),
    ("Mexique", "Corée du Sud"): (1.80, 3.65, 4.70),
    ("États-Unis", "Australie"): (1.77, 3.95, 4.50),
    ("Écosse", "Maroc"): (4.20, 3.30, 2.00),
    ("Brésil", "Haïti"): (1.08, 13.0, 26.0),
    ("Turquie", "Paraguay"): (2.25, 3.20, 3.45),
    ("Pays-Bas", "Suède"): (1.65, 4.20, 5.25),
    ("Allemagne", "Côte d'Ivoire"): (1.56, 4.40, 5.75),
    ("Équateur", "Curaçao"): (1.20, 7.50, 13.0),
    ("Espagne", "Arabie saoudite"): (1.08, 12.0, 26.0),
    ("Tunisie", "Japon"): (4.30, 3.80, 1.75),
    ("Arabie saoudite", "Uruguay"): (8.00, 4.50, 1.43),
    ("Iran", "Nouvelle-Zélande"): (1.91, 3.45, 4.40),
}


def _with_odds(m: MppMatch) -> MppMatch:
    key = (m.home, m.away)
    if key in ESPN_ODDS:
        oh, od, oa = ESPN_ODDS[key]
        m.odds_home, m.odds_draw, m.odds_away = oh, od, oa
    return m


MATCHES: list[MppMatch] = [_with_odds(m) for m in [
    # Jeudi 11 juin
    MppMatch("11/06", "Mexique", "Afrique du Sud", 41, 113, 115, 63, 21, 16),
    MppMatch("11/06", "Corée du Sud", "Tchéquie", 165, 215, 190, 28, 35, 37),  # approx from ESPN
    MppMatch("12/06", "Canada", "Bosnie-Herzégovine", 71, 104, 148, 78, 16, 6),
    # Vendredi 13 / Samedi 14
    MppMatch("13/06", "États-Unis", "Paraguay", 74, 113, 115, 63, 21, 16),
    MppMatch("13/06", "Qatar", "Suisse", 172, 141, 33, 6, 7, 87),
    MppMatch("14/06", "Brésil", "Maroc", 55, 122, 140, 50, 31, 19),
    MppMatch("14/06", "Haïti", "Écosse", 174, 142, 32, 6, 7, 87),
    # Jeudi 18
    MppMatch("18/06", "Angleterre", "Croatie", 59, 119, 133, 57, 35, 8),
    MppMatch("18/06", "Ghana", "Panama", 73, 113, 116, 60, 33, 7),
    MppMatch("18/06", "Ouzbékistan", "Colombie", 157, 130, 44, 3, 7, 90),
    MppMatch("18/06", "Tchéquie", "Afrique du Sud", 62, 112, 142, 57, 28, 15),
    # Vendredi 19
    MppMatch("19/06", "Suisse", "Bosnie-Herzégovine", 76, 108, 134, 76, 19, 5),
    MppMatch("19/06", "Canada", "Qatar", 71, 104, 148, 78, 16, 6),
    MppMatch("19/06", "Mexique", "Corée du Sud", 69, 117, 129, 60, 28, 12),
    MppMatch("19/06", "États-Unis", "Australie", 58, 119, 153, 67, 24, 9),
    # Mardi 16
    MppMatch("16/06", "Arabie saoudite", "Uruguay", 146, 125, 50, 6, 14, 80),
    MppMatch("16/06", "Iran", "Nouvelle-Zélande", 63, 116, 130, 36, 44, 20),
    MppMatch("16/06", "France", "Sénégal", 46, 128, 153, 88, 9, 3),
    # Mercredi 17
    MppMatch("17/06", "Irak", "Norvège", 178, 144, 30, 2, 6, 92),
    MppMatch("17/06", "Argentine", "Algérie", 43, 129, 159, 80, 14, 6),
    MppMatch("17/06", "Autriche", "Jordanie", 38, 136, 163, 85, 12, 3),
    MppMatch("17/06", "Portugal", "RD Congo", 34, 140, 170, 96, 3, 1),
    # Samedi 20
    MppMatch("20/06", "Allemagne", "Côte d'Ivoire", 38, 137, 164, 81, 13, 6),
    MppMatch("20/06", "Équateur", "Curaçao", 41, 143, 168, 85, 12, 3),
    MppMatch("20/06", "Tunisie", "Japon", 118, 103, 91, 15, 29, 56),
    MppMatch("20/06", "Espagne", "Arabie saoudite", 31, 139, 176, 97, 2, 1),
    # Lundi 22
    MppMatch("22/06", "Belgique", "Iran", 39, 138, 171, 93, 5, 2),
    MppMatch("22/06", "Uruguay", "Cap-Vert", 72, 109, 137, 87, 10, 3),
    MppMatch("22/06", "Nouvelle-Zélande", "Égypte", 148, 116, 59, 10, 20, 71),
    MppMatch("22/06", "Argentine", "Autriche", 63, 105, 132, 85, 12, 3),
    # Mardi 23
    MppMatch("23/06", "France", "Irak", 22, 166, 189, 98, 1, 1),
    MppMatch("23/06", "Norvège", "Sénégal", 64, 105, 137, 34, 42, 24),
    MppMatch("23/06", "Jordanie", "Algérie", 152, 139, 67, 4, 13, 83),
    MppMatch("23/06", "Portugal", "Ouzbékistan", 24, 154, 173, 97, 2, 1),
    # Mercredi 24
    MppMatch("24/06", "Angleterre", "Ghana", 44, 127, 162, 89, 9, 3),
    MppMatch("24/06", "Panama", "Croatie", 165, 123, 36, 3, 7, 90),
    MppMatch("24/06", "Colombie", "RD Congo", 77, 111, 123, 71, 23, 6),
    MppMatch("24/06", "Suisse", "Canada", 68, 106, 129, 54, 38, 8),
    # Jeudi 25
    MppMatch("25/06", "Bosnie-Herzégovine", "Qatar", 87, 102, 120, 56, 33, 11),
    MppMatch("25/06", "Écosse", "Brésil", 145, 124, 48, 4, 8, 88),
    MppMatch("25/06", "Maroc", "Haïti", 29, 159, 187, 95, 3, 2),
    MppMatch("25/06", "Tchéquie", "Mexique", 109, 99, 91, 10, 43, 46),
    # Samedi 20 (J2)
    MppMatch("20/06", "Écosse", "Maroc", 99, 112, 91, 7, 24, 69),
    MppMatch("20/06", "Brésil", "Haïti", 21, 167, 198, 97, 2, 1),
    MppMatch("20/06", "Turquie", "Paraguay", 84, 113, 126, 59, 30, 11),
    MppMatch("20/06", "Pays-Bas", "Suède", 67, 122, 131, 65, 28, 7),
    # Jeudi 25 J3
    MppMatch("25/06", "Afrique du Sud", "Corée du Sud", 117, 103, 87, 15, 34, 51),
    MppMatch("25/06", "Équateur", "Allemagne", 145, 129, 42, 4, 12, 84),
    MppMatch("25/06", "Curaçao", "Côte d'Ivoire", 163, 118, 53, 3, 7, 90),
    MppMatch("26/06", "Tunisie", "Pays-Bas", 131, 123, 56, 5, 14, 81),
    MppMatch("26/06", "Turquie", "États-Unis", 109, 102, 93, 33, 42, 25),
    MppMatch("26/06", "Paraguay", "Australie", 74, 104, 131, 53, 33, 14),
    MppMatch("26/06", "Japon", "Suède", 96, 108, 111, 32, 48, 20),
    # Samedi 27
    MppMatch("27/06", "Norvège", "France", 141, 108, 68, 5, 19, 77),
    MppMatch("27/06", "Sénégal", "Irak", 54, 115, 149, 91, 6, 2),
    MppMatch("27/06", "Uruguay", "Espagne", 143, 112, 57, 3, 14, 83),
    MppMatch("27/06", "Cap-Vert", "Arabie saoudite", 99, 123, 94, 14, 55, 31),
    # Dimanche 28
    MppMatch("28/06", "Nouvelle-Zélande", "Belgique", 172, 129, 32, 3, 5, 92),
    MppMatch("28/06", "Égypte", "Iran", 85, 114, 123, 65, 29, 6),
    MppMatch("28/06", "Panama", "Angleterre", 168, 137, 32, 2, 3, 94),
    MppMatch("28/06", "Croatie", "Ghana", 57, 120, 138, 73, 21, 6),
    MppMatch("28/06", "Colombie", "Portugal", 154, 102, 55, 5, 19, 76),
    MppMatch("28/06", "RD Congo", "Ouzbékistan", 63, 107, 158, 64, 29, 7),
    MppMatch("28/06", "Jordanie", "Argentine", 165, 145, 32, 2, 3, 95),
    MppMatch("28/06", "Algérie", "Autriche", 96, 103, 107, 35, 46, 19),
]]


def analyze(m: MppMatch) -> dict:
    if m.odds_home:
        lh, la, blend = fit_lambdas_from_decimal(m.odds_home, m.odds_draw, m.odds_away)
    else:
        probs = mpp_probs(m.pts_home, m.pts_draw, m.pts_away)
        lh, la, blend = fit_lambdas_from_decimal(
            200 / m.pts_home, 200 / m.pts_draw, 200 / m.pts_away
        )

    matrix = score_matrix(lh, la)
    top = top_exact_scores(matrix, 12)
    score, note = pick_mpp_score_v2(
        top,
        blend["home"],
        blend["draw"],
        blend["away"],
        m.crowd_home,
        m.crowd_draw,
        m.crowd_away,
    )
    return {
        "date": m.date,
        "match": f"{m.home} - {m.away}",
        "score": score,
        "p1": f"{blend['home']*100:.0f}%",
        "pN": f"{blend['draw']*100:.0f}%",
        "p2": f"{blend['away']*100:.0f}%",
        "lh": lh,
        "la": la,
        "stat": top[0][0],
        "note": note,
    }


def main() -> None:
    print("=" * 72)
    print("GRILLE MPP CDM 2026 — Scores exacts conseillés")
    print("⚠️  Estimations probabilistes — pas des certitudes")
    print("=" * 72)

    by_date: dict[str, list] = {}
    for m in MATCHES:
        r = analyze(m)
        by_date.setdefault(m.date, []).append(r)

    for date in sorted(by_date.keys(), key=lambda d: tuple(map(int, d.split("/")[::-1]))):
        print(f"\n### {date}")
        print(f"{'Match':<42} {'SCORE':>5}  {'1/N/2':>14}  Note")
        print("-" * 72)
        for r in by_date[date]:
            probs = f"{r['p1']}/{r['pN']}/{r['p2']}"
            print(f"{r['match']:<42} {r['score']:>5}  {probs:>14}  {r['note']}")

    print("\n" + "=" * 72)


if __name__ == "__main__":
    main()
