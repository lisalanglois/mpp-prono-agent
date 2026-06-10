"""Stratégie de sélection du score Mon Petit Prono."""

from __future__ import annotations

from mpp.models.poisson import MPP_CROWD_SCORES


def pick_mpp_score(
    top_scores: list[tuple[str, float]],
    confidence: str,
    outcome_probs: dict[str, float] | None = None,
) -> tuple[str, float, str]:
    """
    Choisit le score conseillé pour MPP.

    Returns:
        (score, probabilité, justification)
    """
    if not top_scores:
        return "1-1", 0.0, "Aucune donnée — score neutre par défaut."

    stat_score, stat_prob = top_scores[0]

    if confidence == "faible":
        return (
            stat_score,
            stat_prob,
            "Confiance faible : on conserve le score statistique le plus probable.",
        )

    # Chercher une alternative moins banale si proche en probabilité
    for score, prob in top_scores[1:6]:
        if score in MPP_CROWD_SCORES:
            continue
        if prob >= stat_prob * 0.60:
            gap_pct = (stat_prob - prob) * 100
            return (
                score,
                prob,
                f"Score #{top_scores.index((score, prob)) + 1} "
                f"({prob * 100:.1f} % vs {stat_prob * 100:.1f} % pour {stat_score}), "
                f"moins banal en grille MPP (écart {gap_pct:.1f} pts).",
            )

    # Si le #1 est banal, prendre le meilleur non-banal dans le top 5
    if stat_score in MPP_CROWD_SCORES:
        for score, prob in top_scores[1:5]:
            if score not in MPP_CROWD_SCORES and prob >= stat_prob * 0.55:
                return (
                    score,
                    prob,
                    f"Le score statistique {stat_score} est très joué en MPP ; "
                    f"alternative {score} avec probabilité encore respectable.",
                )

    # Match très équilibré → nul ou score serré différenciant
    if outcome_probs and outcome_probs.get("draw", 0) > 0.28:
        for score in ("2-2", "0-0", "1-1"):
            for s, p in top_scores[:8]:
                if s == score and s not in (stat_score,) and confidence != "faible":
                    if score == "2-2" and p >= stat_prob * 0.45:
                        return (
                            score,
                            p,
                            "Match équilibré avec probabilité nul élevée ; "
                            "2-2 différencie sans être aberrant.",
                        )

    return (
        stat_score,
        stat_prob,
        "Le score statistique domine nettement — pas de gain clair à différencier.",
    )
