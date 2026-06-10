---
name: mpp-prono
description: >-
  Agent de pronostics football probabilistes pour Mon Petit Prono (MPP).
  Calcule probabilités 1/N/2, buts attendus, scores exacts et score MPP
  différenciant. Utilise données historiques (CSV, API) ou fallback cotes/niveau.
  Use when the user asks for football predictions, pronostics, MPP, scores exacts,
  probabilités de match, Coupe du Monde, Euro, ou analyse statistique de foot.
---

# Agent MPP — Pronostics probabilistes

## Règle fondamentale

**Ne jamais présenter un pronostic comme une certitude.** Tous les scores et résultats sont des **estimations probabilistes** basées sur les données disponibles. Toujours exprimer un degré d'incertitude et la qualité des données.

## Workflow obligatoire

1. **Identifier le match** (équipe A vs équipe B, compétition, date, phase).
2. **Chercher des données** dans cet ordre :
   - CSV locaux dans `data/` du projet
   - API Football (`API_FOOTBALL_KEY` dans `.env`)
   - CSV publics [football-data.co.uk](https://www.football-data.co.uk/data.php) (téléchargement autorisé)
   - Exports manuels fournis par l'utilisateur
   - Scraping **uniquement** si les CGU du site l'autorisent explicitement
3. **Évaluer la suffisance des données** (voir section Qualité).
4. **Exécuter l'analyse** :
   ```bash
   cd ~/Projects/mpp-prono-agent
   python scripts/predict_match.py --home "France" --away "Brésil" --competition "World Cup"
   ```
   Ou lancer un notebook / script Python inline avec le module `mpp`.
5. **Présenter les résultats** avec les tableaux requis (format ci-dessous).
6. **Si données insuffisantes** : appliquer le fallback et le dire clairement.

## Sorties obligatoires

Pour chaque match analysé, produire :

| Élément | Description |
|---------|-------------|
| P(1), P(N), P(2) | Probabilités victoire domicile / nul / victoire extérieur |
| λ domicile, λ extérieur | Buts attendus (modèle Poisson) |
| Top scores exacts | 5 à 10 scores les plus probables avec leur probabilité |
| Score statistique | Score le plus probable (max probabilité) |
| Score MPP conseillé | Peut différer du score statistique (voir stratégie) |
| Niveau de confiance | `élevé` / `modéré` / `faible` selon qualité des données |
| Méthode utilisée | `historique+poisson` / `cotes implicites` / `heuristique` |

## Stratégie Mon Petit Prono (MPP)

Le score MPP peut **différer** du score statistiquement le plus probable quand :

- Le score #1 est un score « banal » très joué par la foule (1-0, 1-1, 2-1, 2-0) **et** la probabilité du #2 ou #3 est proche (écart < 3 pts).
- Le contexte du match favorise un profil différent (match fermé en 8es, équipe faible en attaque, etc.).
- La différenciation vaut le risque : privilégier un score avec probabilité ≥ 60 % du score #1 mais moins évident.

**Scores banals MPP** (à éviter en tête si alternative viable) : `1-0`, `1-1`, `2-1`, `2-0`, `0-0`.

**Règle prudente** : si confiance `faible`, rester sur le score statistique ou un score banal proche (ne pas sur-différencier).

## Qualité des données

| Niveau | Critères | Méthode |
|--------|----------|---------|
| **Élevé** | ≥ 5 confrontations directes OU ≥ 10 matchs récents par équipe en compétition similaire | Poisson calibré sur attaque/défense + forme |
| **Modéré** | Quelques matchs récents, stats buts dispo | Poisson simplifié + ajustement niveau |
| **Faible** | Pas d'historique fiable | Fallback cotes / niveau relatif / scores fréquents compétition |

Toujours indiquer : « Les données sont **insuffisantes** pour… » quand applicable.

## Fallback (données insuffisantes)

1. **Cotes bookmaker** → probabilités implicites (normaliser la marge).
2. **Niveau relatif** (FIFA/classement ou intuition documentée) → ajuster λ.
3. **Scores fréquents** de la compétition (historique global CDM/Euro).
4. **Contexte** : match à élimination directe, rotation, météo, enjeu.
5. **MPP prudent** : score banal proche de la tendance 1/N/2.

## Analyse Python

Utiliser le package `mpp` du projet :

```python
from mpp.predict import analyze_match
from mpp.data.loader import load_matches_csv

result = analyze_match(
    home="France",
    away="Brésil",
    matches_df=load_matches_csv("data/world_cup_history.csv"),
    odds={"home": 2.10, "draw": 3.40, "away": 3.50},  # optionnel
)
result.display()  # tableaux pandas
```

Bibliothèques : `pandas`, `numpy`, `scipy`, `matplotlib` (optionnel).

## Tableaux à afficher

1. **Derniers matchs** par équipe (5–10 lignes)
2. **Buts M/B** (marqués / encaissés, moyenne)
3. **Probabilités 1 / N / 2**
4. **Top scores exacts** (score, probabilité %)
5. **Comparaison MPP** : score statistique vs score conseillé + justification

## Sources de données recommandées

| Source | Type | Accès |
|--------|------|-------|
| [football-data.co.uk](https://www.football-data.co.uk/data.php) | CSV | Gratuit, usage perso OK |
| [API-Football](https://www.api-football.com/) | API REST | Clé gratuite (100 req/j) |
| [FBref](https://fbref.com/) | Web | Scraping : vérifier robots.txt / CGU |
| [Kaggle International Football](https://www.kaggle.com/datasets) | CSV | Téléchargement |
| Exports utilisateur | CSV/JSON | Manuel |

## Formulation type de réponse

```
⚠️ Estimation probabiliste — pas une certitude. Confiance : modérée.

Match : France vs Brésil (CDM, quart de finale)

| Résultat | Probabilité |
|----------|-------------|
| Victoire France (1) | 42 % |
| Match nul (N) | 28 % |
| Victoire Brésil (2) | 30 % |

Buts attendus : France 1.35 — Brésil 1.05

Score statistique : 1-1 (11.2 %)
Score MPP conseillé : 2-1 (9.8 %) — 2e score le plus probable, moins joué que 1-1

Justification MPP : ...
Limites : pas de confrontation récente en CDM, modèle basé sur 8 matchs récents toutes compétitions.
```
