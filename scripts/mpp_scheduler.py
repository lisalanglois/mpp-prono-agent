#!/usr/bin/env python3
"""
Planificateur MPP multi-compétitions (CDM, Euro, …).

Automatique :
  • J-7 à J-1 : email avec grille complète + pronos globaux + URLs
  • Pendant la comp : rappels avant chaque match (via live_tracker)
  • Après la fin : email de clôture + arrêt des rappels match

Usage:
  python scripts/mpp_scheduler.py
  python scripts/mpp_scheduler.py --pre-comp cdm2026 --dry-run
  python scripts/mpp_scheduler.py --email
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from competition_emails import send_closing_email, send_pre_competition_email
from mpp.competitions import (
    get_active_competition,
    get_competition,
    get_recently_ended,
    get_upcoming_pre_alert,
    list_competitions,
)

STATE_FILE = ROOT / "data" / "scheduler_state.json"


def load_scheduler_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"pre_comp_sent": [], "closing_sent": []}


def save_scheduler_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def process_pre_competition(state: dict, *, dry_run: bool = False, force_id: str | None = None) -> int:
    sent = 0
    targets = []
    if force_id:
        c = get_competition(force_id)
        if c:
            c = dict(c)
            c["days_until_start"] = 7
            targets = [c]
    else:
        targets = get_upcoming_pre_alert()

    for comp in targets:
        if comp["id"] in state.get("pre_comp_sent", []):
            continue
        print(f"📬 Email J-{comp['days_until_start']} : {comp['name']}")
        if send_pre_competition_email(comp, dry_run=dry_run):
            if not dry_run:
                state.setdefault("pre_comp_sent", []).append(comp["id"])
            sent += 1
    return sent


def process_closing(state: dict, *, dry_run: bool = False) -> int:
    sent = 0
    tracker = {}
    tracker_path = ROOT / "data" / "live_tracker.json"
    if tracker_path.exists():
        tracker = json.loads(tracker_path.read_text(encoding="utf-8"))

    for comp in get_recently_ended():
        if comp["id"] in state.get("closing_sent", []):
            continue
        print(f"🏁 Email clôture : {comp['name']}")
        if send_closing_email(comp, tracker, dry_run=dry_run):
            if not dry_run:
                state.setdefault("closing_sent", []).append(comp["id"])
            sent += 1
    return sent


def process_live_tracking(args: argparse.Namespace) -> None:
    active = get_active_competition()
    if not active:
        print("ℹ️  Aucune compétition en cours — pas de live tracker")
        return
    print(f"⚽ Compétition active : {active['name']}")
    import live_tracker
    live_tracker.main(
        comp=active,
        force_email=args.email,
        force_dry_run_email=args.dry_run_email,
        _from_scheduler=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Planificateur MPP multi-compétitions")
    parser.add_argument("--pre-comp", metavar="ID", help="Forcer email J-7 (ex. cdm2026, euro2028)")
    parser.add_argument("--dry-run", action="store_true", help="Afficher sans envoyer")
    parser.add_argument("--email", action="store_true", help="Forcer envoi emails live tracker")
    parser.add_argument("--dry-run-email", action="store_true")
    parser.add_argument("--list", action="store_true", help="Lister les compétitions")
    args = parser.parse_args()

    if args.list:
        today = date.today()
        for c in list_competitions():
            start, end = c["start"], c["end"]
            status = "à venir"
            if start <= str(today) <= end:
                status = "EN COURS"
            elif str(today) > end:
                status = "terminée"
            print(f"  {c['id']:12} {c['short']:10} {start} → {end}  [{status}]")
        return

    state = load_scheduler_state()

    n_pre = process_pre_competition(
        state, dry_run=args.dry_run, force_id=args.pre_comp
    )
    process_live_tracking(args)
    n_close = process_closing(state, dry_run=args.dry_run)

    if not args.dry_run:
        save_scheduler_state(state)

    print(f"\n✅ Scheduler — pre:{n_pre} closing:{n_close}")


if __name__ == "__main__":
    main()
