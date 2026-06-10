# MPP Prono Agent

Agent de pronostics football **probabilistes** pour [Mon Petit Prono](https://www.monpetitprono.com/). Les scores proposés sont des estimations, jamais des certitudes.

## Installation

```bash
cd ~/Projects/mpp-prono-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Site web (plus simple que l'app MPP)

```bash
python scripts/serve_web.py
```

Ouvre **http://localhost:8765** dans ton navigateur :
- Tous les matchs par date
- Scores suggérés par l'IA (clic pour appliquer)
- Sauvegarde automatique dans le navigateur
- Bouton « Copier ma grille » pour recopier dans MPP si besoin

## Usage rapide (CLI)

```bash
# ⭐ Pronostics du jour (cotes ESPN live + forme récente)
python scripts/prono_today.py

# Match spécifique demain
python scripts/prono_today.py --match "Mexico" "South Africa"

# Analyse manuelle avec CSV
python scripts/predict_match.py \
  --home "France" \
  --away "Espagne" \
  --data data/cdm2026_form.csv
```

## Modèle

- **Poisson indépendant** pour la matrice de scores exacts
- Forces attaque/défense calibrées sur les buts marqués/encaissés récents
- Probabilités **1 / N / 2** par sommation sur la matrice
- **Stratégie MPP** : différenciation intelligente vs scores banals (1-0, 1-1, 2-1…)

## Sources de données

| Source | Usage |
|--------|-------|
| CSV local (`data/`) | Prioritaire |
| [football-data.co.uk](https://www.football-data.co.uk/data.php) | CSV gratuits |
| API-Football | `API_FOOTBALL_KEY` dans `.env` |
| Cotes bookmaker | Fallback `--odds-*` |

## Skill Cursor

Le skill `.cursor/skills/mpp-prono/SKILL.md` guide l'agent Cursor pour produire des analyses conformes (tableaux, disclaimers, stratégie MPP).

Pour l'activer : mentionner « pronostic MPP », « Mon Petit Prono », ou invoquer le skill `mpp-prono`.

## Python API

```python
import sys
sys.path.insert(0, "src")

from mpp.predict import analyze_match
from mpp.data.loader import load_matches_csv

df = load_matches_csv("data/sample_international.csv")
result = analyze_match("France", "Espagne", matches_df=df, competition="Euro")
result.display()
```

## GitHub + automatisation

### Mettre sur GitHub

```bash
cd ~/Projects/mpp-prono-agent
git add .
git commit -m "feat: agent pronos MPP CDM 2026"
gh repo create mpp-prono-agent --private --source=. --push
```

### Pronos du jour (automatique)

```bash
python scripts/export_daily.py          # → data/daily_predictions.json
python scripts/export_daily.py --stdout # afficher le JSON
```

**GitHub Actions** (`.github/workflows/daily-pronos.yml`) :
- Tourne **tous les jours à 8h UTC**
- Récupère les matchs ESPN + génère les scores
- Commit `data/daily_predictions.json` + `web/matches.json`
- Déploie le site sur **GitHub Pages**

Activer Pages : repo → Settings → Pages → Source = **GitHub Actions**.

### Remplissage auto sur mpp.football ?

| Faisable | Détail |
|----------|--------|
| ✅ Générer pronos | ESPN + Poisson + overrides (`export_daily.py`) |
| ✅ Site / JSON à jour | GitHub Actions + Pages |
| ✅ Copier-coller rapide | `mpp_copy` dans le JSON du jour |
| ❌ Saisie directe MPP | Pas d'API officielle Mon Petit Prono |

**Workflow recommandé :**
1. GitHub Action génère les pronos chaque matin
2. Tu ouvres `data/daily_predictions.json` ou la page GitHub Pages
3. Tu recopies les scores sur [mpp.football](https://mpp.football) (2 min)

Une automatisation Playwright (login + remplissage) serait possible mais fragile et déconseillée (CGU, mot de passe à stocker).

## Limites

- Modèle Poisson simplifié (pas de Dixon-Coles complet)
- Qualité des prédictions = qualité des données
- Toujours interpréter les résultats comme des **probabilités**, pas des faits
