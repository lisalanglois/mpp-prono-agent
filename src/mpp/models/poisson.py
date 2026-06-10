"""Modèle de Poisson pour scores de football."""

from __future__ import annotations

import numpy as np
from scipy.stats import poisson


# Scores très fréquents en compétitions internationales (football-data / CDM historique)
DEFAULT_INTERNATIONAL_SCORE_FREQ = {
    "1-0": 0.115,
    "2-1": 0.095,
    "1-1": 0.110,
    "2-0": 0.085,
    "0-0": 0.075,
    "0-1": 0.070,
    "3-1": 0.055,
    "2-2": 0.050,
    "1-2": 0.065,
    "3-0": 0.045,
}

# Scores « banals » souvent sur-représentés dans les grilles MPP
MPP_CROWD_SCORES = frozenset({"1-0", "1-1", "2-1", "2-0", "0-0"})

HOME_ADVANTAGE = 1.10  # léger avantage domicile en compétitions internationales


def score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 6) -> np.ndarray:
    """Matrice de probabilités P(home=i, away=j) via Poisson indépendant."""
    home_probs = poisson.pmf(np.arange(max_goals + 1), lambda_home)
    away_probs = poisson.pmf(np.arange(max_goals + 1), lambda_away)
    return np.outer(home_probs, away_probs)


def outcome_probabilities(matrix: np.ndarray) -> dict[str, float]:
    """Probabilités 1 / N / 2 à partir de la matrice de scores."""
    n = matrix.shape[0]
    p_home = sum(matrix[i, j] for i in range(n) for j in range(n) if i > j)
    p_draw = sum(matrix[i, i] for i in range(n))
    p_away = sum(matrix[i, j] for i in range(n) for j in range(n) if i < j)
    total = p_home + p_draw + p_away
    if total <= 0:
        return {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}
    return {
        "home": p_home / total,
        "draw": p_draw / total,
        "away": p_away / total,
    }


def top_exact_scores(
    matrix: np.ndarray, top_n: int = 10
) -> list[tuple[str, float]]:
    """Retourne les scores exacts les plus probables."""
    flat = []
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            flat.append((f"{i}-{j}", float(matrix[i, j])))
    flat.sort(key=lambda x: x[1], reverse=True)
    return flat[:top_n]


def estimate_lambdas_from_stats(
    home_scored: float,
    home_conceded: float,
    away_scored: float,
    away_conceded: float,
    league_avg: float = 1.25,
    home_advantage: float = HOME_ADVANTAGE,
) -> tuple[float, float]:
    """
    Estime λ domicile et λ extérieur via forces d'attaque/défense relatives.
    Formule type Dixon-Coles simplifiée (Poisson indépendant).
    """
    if league_avg <= 0:
        league_avg = 1.25

    home_attack = home_scored / league_avg
    home_defense = home_conceded / league_avg
    away_attack = away_scored / league_avg
    away_defense = away_conceded / league_avg

    lambda_home = max(0.15, home_attack * away_defense * league_avg * home_advantage)
    lambda_away = max(0.15, away_attack * home_defense * league_avg)
    return lambda_home, lambda_away


def lambdas_from_odds(
    odds_home: float,
    odds_draw: float,
    odds_away: float,
    league_avg: float = 1.25,
) -> tuple[float, float, dict[str, float]]:
    """
    Fallback : dérive λ et probabilités 1/N/2 depuis les cotes implicites.
    Utilise une heuristique pour répartir les buts selon le favori.
    """
    implied = {
        "home": 1 / odds_home,
        "draw": 1 / odds_draw,
        "away": 1 / odds_away,
    }
    margin = sum(implied.values())
    probs = {k: v / margin for k, v in implied.items()}

    # Heuristique : total buts attendus ~ 2.5 en matchs internationaux serrés
    total_goals = league_avg * 2.0
    if probs["home"] > probs["away"]:
        ratio = probs["home"] / max(probs["away"], 0.05)
        lambda_home = total_goals * (ratio / (1 + ratio)) * 0.55 + 0.4
        lambda_away = total_goals - lambda_home + 0.2
    elif probs["away"] > probs["home"]:
        ratio = probs["away"] / max(probs["home"], 0.05)
        lambda_away = total_goals * (ratio / (1 + ratio)) * 0.55 + 0.4
        lambda_home = total_goals - lambda_away + 0.2
    else:
        lambda_home = league_avg * HOME_ADVANTAGE
        lambda_away = league_avg

    return max(0.15, lambda_home), max(0.15, lambda_away), probs
