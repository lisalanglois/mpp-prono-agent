"""Module principal d'analyse de match."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from mpp.data.loader import (
    head_to_head,
    league_average_goals,
    score_frequency_table,
    team_goals_stats,
    team_recent_matches,
)
from mpp.models.poisson import (
    estimate_lambdas_from_stats,
    lambdas_from_odds,
    outcome_probabilities,
    score_matrix,
    top_exact_scores,
)
from mpp.mpp_strategy import pick_mpp_score


@dataclass
class MatchAnalysis:
    home: str
    away: str
    competition: str | None
    confidence: str
    method: str
    lambda_home: float
    lambda_away: float
    outcome_probs: dict[str, float]
    top_scores: list[tuple[str, float]]
    stat_score: str
    stat_prob: float
    mpp_score: str
    mpp_prob: float
    mpp_justification: str
    home_recent: pd.DataFrame = field(default_factory=pd.DataFrame)
    away_recent: pd.DataFrame = field(default_factory=pd.DataFrame)
    goals_stats: pd.DataFrame = field(default_factory=pd.DataFrame)
    h2h: pd.DataFrame = field(default_factory=pd.DataFrame)
    score_freq: pd.DataFrame = field(default_factory=pd.DataFrame)
    warnings: list[str] = field(default_factory=list)

    def outcome_table(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Résultat": ["Victoire domicile (1)", "Match nul (N)", "Victoire extérieur (2)"],
                "Probabilité": [
                    f"{self.outcome_probs['home'] * 100:.1f} %",
                    f"{self.outcome_probs['draw'] * 100:.1f} %",
                    f"{self.outcome_probs['away'] * 100:.1f} %",
                ],
            }
        )

    def expected_goals_table(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Équipe": [self.home, self.away],
                "Buts attendus (λ)": [f"{self.lambda_home:.2f}", f"{self.lambda_away:.2f}"],
            }
        )

    def top_scores_table(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Score": [s for s, _ in self.top_scores],
                "Probabilité": [f"{p * 100:.2f} %" for _, p in self.top_scores],
            }
        )

    def mpp_comparison_table(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Type": ["Score statistique", "Score MPP conseillé"],
                "Score": [self.stat_score, self.mpp_score],
                "Probabilité": [
                    f"{self.stat_prob * 100:.2f} %",
                    f"{self.mpp_prob * 100:.2f} %",
                ],
                "Note": ["Max probabilité", self.mpp_justification],
            }
        )

    def display(self) -> None:
        """Affiche tous les tableaux."""
        print(f"\n{'=' * 60}")
        print(f"⚠️  ESTIMATION PROBABILISTE — pas une certitude")
        print(f"Match : {self.home} vs {self.away}")
        if self.competition:
            print(f"Compétition : {self.competition}")
        print(f"Confiance : {self.confidence} | Méthode : {self.method}")
        if self.warnings:
            for w in self.warnings:
                print(f"⚠️  {w}")
        print(f"{'=' * 60}\n")

        print("--- Probabilités 1 / N / 2 ---")
        print(self.outcome_table().to_string(index=False))
        print("\n--- Buts attendus ---")
        print(self.expected_goals_table().to_string(index=False))
        print("\n--- Top scores exacts ---")
        print(self.top_scores_table().to_string(index=False))
        print("\n--- Comparaison MPP ---")
        print(self.mpp_comparison_table().to_string(index=False))

        if not self.goals_stats.empty:
            print("\n--- Buts M/B (moyennes récentes) ---")
            print(self.goals_stats.to_string(index=False))


def _assess_confidence(
    home_matches: int, away_matches: int, h2h_count: int
) -> str:
    total = home_matches + away_matches
    if h2h_count >= 3 and min(home_matches, away_matches) >= 5:
        return "élevé"
    if total >= 8 and min(home_matches, away_matches) >= 3:
        return "modéré"
    return "faible"


def analyze_match(
    home: str,
    away: str,
    matches_df: pd.DataFrame | None = None,
    competition: str | None = None,
    odds: dict[str, float] | None = None,
    recent_n: int = 10,
) -> MatchAnalysis:
    """
    Analyse probabiliste complète d'un match.

    Args:
        home: Équipe domicile
        away: Équipe extérieur
        matches_df: DataFrame historique (optionnel)
        competition: Filtre compétition
        odds: {"home": 2.1, "draw": 3.4, "away": 3.5} (optionnel)
        recent_n: Nombre de matchs récents pour les stats
    """
    warnings: list[str] = []
    method = "heuristique"
    outcome_from_odds: dict[str, float] | None = None

    home_stats = {"scored": 1.25, "conceded": 1.25, "matches": 0}
    away_stats = {"scored": 1.25, "conceded": 1.25, "matches": 0}
    h2h_df = pd.DataFrame()
    home_recent = pd.DataFrame()
    away_recent = pd.DataFrame()
    score_freq = pd.DataFrame()
    league_avg = 1.25

    if matches_df is not None and not matches_df.empty:
        home_stats = team_goals_stats(matches_df, home, recent_n, competition)
        away_stats = team_goals_stats(matches_df, away, recent_n, competition)
        h2h_df = head_to_head(matches_df, home, away)
        home_recent = team_recent_matches(matches_df, home, recent_n, competition)
        away_recent = team_recent_matches(matches_df, away, recent_n, competition)
        score_freq = score_frequency_table(matches_df)
        league_avg = league_average_goals(matches_df, competition)

        if home_stats["matches"] == 0:
            warnings.append(f"Pas de match récent trouvé pour {home} — moyennes par défaut.")
        if away_stats["matches"] == 0:
            warnings.append(f"Pas de match récent trouvé pour {away} — moyennes par défaut.")
        if h2h_df.empty:
            warnings.append("Aucune confrontation directe dans les données.")

    confidence = _assess_confidence(
        int(home_stats["matches"]), int(away_stats["matches"]), len(h2h_df)
    )

    if home_stats["matches"] > 0 and away_stats["matches"] > 0:
        lambda_home, lambda_away = estimate_lambdas_from_stats(
            home_stats["scored"],
            home_stats["conceded"],
            away_stats["scored"],
            away_stats["conceded"],
            league_avg=league_avg,
        )
        method = "historique+poisson"
    elif odds:
        lambda_home, lambda_away, outcome_from_odds = lambdas_from_odds(
            odds["home"], odds["draw"], odds["away"], league_avg=league_avg
        )
        method = "cotes implicites"
        warnings.append("Données historiques insuffisantes — modèle basé sur les cotes.")
    else:
        lambda_home, lambda_away = 1.35, 1.10
        method = "heuristique"
        warnings.append(
            "Données insuffisantes — estimation par défaut (λ=1.35/1.10). "
            "Fournir un CSV ou des cotes pour améliorer."
        )

    matrix = score_matrix(lambda_home, lambda_away)
    outcome_probs = outcome_from_odds or outcome_probabilities(matrix)
    top_scores = top_exact_scores(matrix, top_n=10)
    stat_score, stat_prob = top_scores[0]

    mpp_score, mpp_prob, mpp_just = pick_mpp_score(
        top_scores, confidence, outcome_probs
    )

    goals_stats = pd.DataFrame(
        [
            {
                "Équipe": home,
                "Marqués (moy.)": f"{home_stats['scored']:.2f}",
                "Encaissés (moy.)": f"{home_stats['conceded']:.2f}",
                "Matchs": int(home_stats["matches"]),
            },
            {
                "Équipe": away,
                "Marqués (moy.)": f"{away_stats['scored']:.2f}",
                "Encaissés (moy.)": f"{away_stats['conceded']:.2f}",
                "Matchs": int(away_stats["matches"]),
            },
        ]
    )

    return MatchAnalysis(
        home=home,
        away=away,
        competition=competition,
        confidence=confidence,
        method=method,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        outcome_probs=outcome_probs,
        top_scores=top_scores,
        stat_score=stat_score,
        stat_prob=stat_prob,
        mpp_score=mpp_score,
        mpp_prob=mpp_prob,
        mpp_justification=mpp_just,
        home_recent=home_recent,
        away_recent=away_recent,
        goals_stats=goals_stats,
        h2h=h2h_df,
        score_freq=score_freq,
        warnings=warnings,
    )
