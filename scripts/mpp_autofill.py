#!/usr/bin/env python3
"""
Remplissage semi-automatique des pronos sur mpp.football (Playwright).

MPP n'a pas d'API publique. Approche recommandée :
  1. Connexion manuelle une fois → session sauvegardée
  2. Script remplit les scores depuis daily_predictions.json ou la grille locale

Usage:
  pip install -r requirements-automation.txt
  playwright install chromium

  # Étape 1 — une seule fois (ou quand la session expire)
  python scripts/mpp_autofill.py login

  # Étape 2 — remplir les matchs à venir
  python scripts/mpp_autofill.py fill --dry-run
  python scripts/mpp_autofill.py fill
  python scripts/mpp_autofill.py fill --today
  python scripts/mpp_autofill.py fill --all

⚠️  Risques : session expirée, changement UI MPP, CGU non garanties.
    Ne jamais committer data/mpp_session.json (déjà dans .gitignore).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

SESSION_FILE = ROOT / "data" / "mpp_session.json"
DAILY_FILE = ROOT / "data" / "daily_predictions.json"
MPP_URL = "https://mpp.football"
MPP_PRONOS_URL = "https://mpp.football/"  # SPA — Mes Pronos après login

# Alias affichage MPP (site peut tronquer les noms)
TEAM_VARIANTS: dict[str, list[str]] = {
    "Bosnie-Herzégovine": ["Bosnie", "Bosnia"],
    "Afrique du Sud": ["Afrique du Sud", "South Africa"],
    "Corée du Sud": ["Corée du Sud", "Korea"],
    "États-Unis": ["États-Unis", "USA", "United States"],
    "Arabie saoudite": ["Arabie saoudite", "Arabie Saoudite"],
}


def load_predictions(today_only: bool, all_matches: bool) -> list[dict]:
    if all_matches:
        from export_web import OVERRIDES
        from mpp_grille_cdm import MATCHES, analyze

        rows = []
        for m in MATCHES:
            key = f"{m.home} - {m.away}"
            score = OVERRIDES.get(key, analyze(m)["score"])
            hg, ag = score.split("-")
            rows.append({"home": m.home, "away": m.away, "score": score, "hg": int(hg), "ag": int(ag)})
        return rows

    if not DAILY_FILE.exists():
        raise SystemExit(f"❌ {DAILY_FILE} introuvable — lancer: python scripts/export_daily.py")

    data = json.loads(DAILY_FILE.read_text())
    rows = []
    today = date.today()

    for p in data.get("predictions", []):
        if "error" in p:
            continue
        kickoff = p.get("kickoff_utc", "")
        if today_only and kickoff:
            try:
                dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).astimezone()
                if dt.date() != today:
                    continue
            except ValueError:
                pass
        hg, ag = p["score"].split("-")
        rows.append({
            "home": p["home"],
            "away": p["away"],
            "score": p["score"],
            "hg": int(hg),
            "ag": int(ag),
        })
    return rows


def team_labels(name: str) -> list[str]:
    labels = [name]
    labels.extend(TEAM_VARIANTS.get(name, []))
    return list(dict.fromkeys(labels))


def ensure_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "❌ Playwright manquant.\n"
            "   pip install -r requirements-automation.txt\n"
            "   playwright install chromium"
        ) from exc


def cmd_login(headless: bool) -> None:
    ensure_playwright()
    from playwright.sync_api import sync_playwright

    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("CONNEXION MPP — session Playwright")
    print("=" * 60)
    print(f"1. Le navigateur s'ouvre sur {MPP_URL}")
    print("2. Connecte-toi (email / Google / Facebook)")
    print("3. Va sur « Mes Pronos » si besoin")
    print("4. Reviens ici et appuie ENTRÉE pour sauvegarder la session")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=80)
        context = browser.new_context(locale="fr-FR")
        page = context.new_page()
        page.goto(MPP_URL, wait_until="domcontentloaded", timeout=60000)
        input("\n⏸  Connecté ? Appuie ENTRÉE pour sauvegarder la session… ")
        context.storage_state(path=str(SESSION_FILE))
        browser.close()

    print(f"✅ Session → {SESSION_FILE}")


def find_match_card(page, home: str, away: str):
    """Trouve la carte match contenant les deux équipes."""
    from playwright.sync_api import Page, Locator

    for home_label in team_labels(home):
        for away_label in team_labels(away):
            try:
                home_loc = page.get_by_text(home_label, exact=False).first
                if home_loc.count() == 0:
                    continue
                # Remonte jusqu'à un conteneur qui contient aussi l'adversaire
                card = home_loc.locator(
                    f"xpath=ancestor::*[contains(normalize-space(.), '{away_label}')][1]"
                )
                if card.count() > 0:
                    return card.first
            except Exception:
                continue

    # Fallback : regex sur tout le texte visible
    pattern = re.compile(re.escape(home[:6]), re.I)
    candidates = page.locator("div, article, li, section").filter(has_text=pattern)
    for i in range(min(candidates.count(), 40)):
        block = candidates.nth(i)
        txt = block.inner_text(timeout=500)
        if any(a in txt for a in team_labels(away)):
            return block
    return None


def fill_score_inputs(card, hg: int, ag: int, dry_run: bool) -> bool:
    """Remplit les 2 champs score dans une carte match."""
    inputs = card.locator(
        "input[type='number'], input[type='text'], input[inputmode='numeric'], input"
    )
    count = inputs.count()
    if count < 2:
        return False

    # Souvent : [home_goals, away_goals]
    if dry_run:
        return True

    inputs.nth(0).click()
    inputs.nth(0).fill("")
    inputs.nth(0).fill(str(hg))
    time.sleep(0.15)
    inputs.nth(1).click()
    inputs.nth(1).fill("")
    inputs.nth(1).fill(str(ag))
    # blur pour déclencher la sauvegarde auto MPP
    inputs.nth(1).press("Tab")
    time.sleep(0.4)
    return True


def cmd_fill(dry_run: bool, today_only: bool, all_matches: bool, headless: bool) -> None:
    ensure_playwright()
    from playwright.sync_api import sync_playwright

    if not SESSION_FILE.exists():
        raise SystemExit("❌ Pas de session — lancer d'abord: python scripts/mpp_autofill.py login")

    predictions = load_predictions(today_only, all_matches)
    if not predictions:
        raise SystemExit("❌ Aucun match à remplir pour les critères choisis.")

    print(f"📋 {len(predictions)} match(s) à traiter" + (" [DRY-RUN]" if dry_run else ""))

    ok, fail = 0, 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=50)
        context = browser.new_context(storage_state=str(SESSION_FILE), locale="fr-FR")
        page = context.new_page()
        page.goto(MPP_URL, wait_until="networkidle", timeout=90000)

        # Attendre la zone pronos
        try:
            page.get_by_text("Mes Pronos", exact=False).first.wait_for(timeout=15000)
        except Exception:
            print("⚠️  « Mes Pronos » non détecté — vérifie que la session est encore valide.")

        for row in predictions:
            home, away, score = row["home"], row["away"], row["score"]
            hg, ag = row["hg"], row["ag"]
            print(f"\n→ {home} - {away} : {score}")

            card = find_match_card(page, home, away)
            if card is None:
                # Scroll pour charger matchs plus bas
                page.mouse.wheel(0, 600)
                time.sleep(0.5)
                card = find_match_card(page, home, away)

            if card is None:
                print("   ❌ Carte match introuvable (nom différent sur le site ?)")
                fail += 1
                continue

            try:
                card.scroll_into_view_if_needed()
            except Exception:
                pass

            if fill_score_inputs(card, hg, ag, dry_run):
                print("   ✅ " + ("simulé" if dry_run else "rempli"))
                ok += 1
            else:
                print("   ❌ Champs score introuvables")
                fail += 1

        if not dry_run:
            context.storage_state(path=str(SESSION_FILE))
        browser.close()

    print("\n" + "=" * 60)
    print(f"Terminé : {ok} OK, {fail} échecs")
    if fail:
        print("💡 Vérifie les noms d'équipes sur MPP ou relance `login` si déconnecté.")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Autofill MPP via Playwright")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_login = sub.add_parser("login", help="Sauvegarder session après connexion manuelle")
    p_login.add_argument("--headless", action="store_true")

    p_fill = sub.add_parser("fill", help="Remplir les pronos")
    p_fill.add_argument("--dry-run", action="store_true", help="Simuler sans saisir")
    p_fill.add_argument("--today", action="store_true", help="Matchs du jour seulement")
    p_fill.add_argument("--all", action="store_true", help="Toute la grille locale (OVERRIDES)")
    p_fill.add_argument("--headless", action="store_true", help="Sans fenêtre (debug off)")

    args = parser.parse_args()

    if args.cmd == "login":
        cmd_login(headless=args.headless)
    elif args.cmd == "fill":
        cmd_fill(
            dry_run=args.dry_run,
            today_only=args.today,
            all_matches=args.all,
            headless=args.headless,
        )


if __name__ == "__main__":
    main()
