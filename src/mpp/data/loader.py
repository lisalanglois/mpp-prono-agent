"""Chargement et préparation des données historiques."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mpp.data.team_aliases import normalize_team


# Colonnes normalisées attendues après chargement
STANDARD_COLUMNS = {
    "date": "date",
    "home_team": "home_team",
    "away_team": "away_team",
    "home_goals": "home_goals",
    "away_goals": "away_goals",
    "competition": "competition",
}

# Mapping football-data.co.uk
FOOTBALL_DATA_UK_MAP = {
    "Date": "date",
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "FTHG": "home_goals",
    "FTAG": "away_goals",
    "Div": "competition",
}


def load_matches_csv(path: str | Path) -> pd.DataFrame:
    """Charge un CSV de matchs et normalise les colonnes."""
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]

    # football-data.co.uk
    if "HomeTeam" in df.columns:
        df = df.rename(columns=FOOTBALL_DATA_UK_MAP)

    # Format custom minimal
    for col in ("home_team", "away_team", "home_goals", "away_goals"):
        if col not in df.columns:
            raise ValueError(f"Colonne manquante : {col} dans {path}")

    if "date" in df.columns:
        # ISO (YYYY-MM-DD) en priorité ; dayfirst pour format football-data.co.uk (DD/MM/YY)
        iso = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
        other = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
        df["date"] = iso.fillna(other)

    for col in ("home_goals", "away_goals"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["home_team", "away_team", "home_goals", "away_goals"])
    return df


def _team_mask(series: pd.Series, team: str) -> pd.Series:
    canonical = normalize_team(team).lower()
    return series.str.lower().isin({team.lower(), canonical.lower()})


def team_recent_matches(
    df: pd.DataFrame, team: str, n: int = 10, competition: str | None = None
) -> pd.DataFrame:
    """Derniers matchs d'une équipe (domicile ou extérieur)."""
    mask = _team_mask(df["home_team"], team) | _team_mask(df["away_team"], team)
    subset = df.loc[mask].copy()
    if competition and "competition" in subset.columns:
        subset = subset[subset["competition"].str.contains(competition, case=False, na=False)]
    if "date" in subset.columns:
        subset = subset.sort_values("date", ascending=False)
    return subset.head(n)


def team_goals_stats(
    df: pd.DataFrame, team: str, n: int = 10, competition: str | None = None
) -> dict[str, float]:
    """Moyennes buts marqués / encaissés sur les n derniers matchs."""
    recent = team_recent_matches(df, team, n, competition)
    if recent.empty:
        return {"scored": 1.25, "conceded": 1.25, "matches": 0}

    scored, conceded = [], []
    canonical = normalize_team(team).lower()
    for _, row in recent.iterrows():
        home = str(row["home_team"]).lower()
        if home == team.lower() or home == canonical:
            scored.append(row["home_goals"])
            conceded.append(row["away_goals"])
        else:
            scored.append(row["away_goals"])
            conceded.append(row["home_goals"])

    return {
        "scored": float(sum(scored) / len(scored)),
        "conceded": float(sum(conceded) / len(conceded)),
        "matches": len(scored),
    }


def head_to_head(df: pd.DataFrame, team_a: str, team_b: str) -> pd.DataFrame:
    """Confrontations directes entre deux équipes."""
    names_a = {team_a.lower(), normalize_team(team_a).lower()}
    names_b = {team_b.lower(), normalize_team(team_b).lower()}
    mask = (
        (df["home_team"].str.lower().isin(names_a | names_b))
        & (df["away_team"].str.lower().isin(names_a | names_b))
        & (df["home_team"].str.lower() != df["away_team"].str.lower())
    )
    # Garder uniquement les matchs entre A et B
    def is_h2h(row: pd.Series) -> bool:
        h, aw = str(row["home_team"]).lower(), str(row["away_team"]).lower()
        return (h in names_a and aw in names_b) or (h in names_b and aw in names_a)

    h2h = df.loc[mask].copy()
    h2h = h2h[h2h.apply(is_h2h, axis=1)]
    if "date" in h2h.columns:
        h2h = h2h.sort_values("date", ascending=False)
    return h2h


def league_average_goals(df: pd.DataFrame, competition: str | None = None) -> float:
    """Moyenne de buts par match dans le dataset."""
    subset = df
    if competition and "competition" in df.columns:
        subset = df[df["competition"].str.contains(competition, case=False, na=False)]
    if subset.empty:
        return 1.25
    return float((subset["home_goals"] + subset["away_goals"]).mean() / 2)


def score_frequency_table(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    """Fréquence historique des scores exacts."""
    scores = df.apply(
        lambda r: f"{int(r['home_goals'])}-{int(r['away_goals'])}", axis=1
    )
    freq = scores.value_counts(normalize=True).head(top_n)
    return pd.DataFrame({"score": freq.index, "frequency": freq.values})
