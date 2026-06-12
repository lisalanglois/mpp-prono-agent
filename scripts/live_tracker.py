#!/usr/bin/env python3
"""
Suivi live CDM 2026 — compare tes pronos vs modèle vs Klement après chaque match.

Usage:
  python scripts/live_tracker.py
  python scripts/live_tracker.py --webhook https://hooks.slack.com/...

Sorties:
  data/live_tracker.json   — état + stats + alertes
  web/tracker.json         — même chose pour le site GitHub Pages

Alertes si:
  - Gros favori perd (revoir vainqueur MPP / parcours)
  - Trajectoire Klement compromise (ex: Brésil passe le 1er tour)
  - 3+ erreurs 1/N/2 consécutives
  - Match joué sans prono enregistré

Email (Lisa + Juliette) après chaque nouveau match terminé :
  - Derniers résultats
  - Pronos à revoir avant match (date, équipes, actuel → suggéré)
  - Alertes éventuelles
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from alert_email import send_alert_email
from export_web import OVERRIDES
from mpp.data.espn import fetch_finished_since
from mpp.data.team_aliases import to_french
from mpp_grille_cdm import MATCHES, analyze, _with_odds

OUT = ROOT / "data" / "live_tracker.json"
WEB_OUT = ROOT / "web" / "tracker.json"
STATE = ROOT / "data" / "live_tracker_state.json"
KLEMENT = ROOT / "data" / "klement_predictions.json"

def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"sent_alerts": []}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def new_alerts_only(alerts: list[dict], state: dict) -> list[dict]:
    sent = set(state.get("sent_alerts", []))
    fresh = []
    for a in alerts:
        key = f"{a['level']}|{a['match']}|{a['message']}"
        if key not in sent:
            fresh.append(a)
    return fresh


HEAVY_FAVORITES = {"France", "Espagne", "Brésil", "Angleterre", "Allemagne", "Argentine", "Portugal"}


def outcome(hg: int, ag: int) -> str:
    if hg > ag:
        return "home"
    if hg < ag:
        return "away"
    return "draw"


def score_outcome(score: str) -> str:
    h, a = map(int, score.split("-"))
    return outcome(h, a)


def actual_score(m: dict) -> str:
    return f"{int(m['home_goals'])}-{int(m['away_goals'])}"


def match_key(home_fr: str, away_fr: str) -> str:
    return f"{home_fr} - {away_fr}"


def load_klement() -> dict:
    if KLEMENT.exists():
        return json.loads(KLEMENT.read_text())
    return {}


def klement_predict(key: str, home: str, away: str, klement: dict) -> str | None:
    explicit = klement.get("explicit_outcomes", {})
    if key in explicit:
        return explicit[key]
    strength = klement.get("team_strength", {})
    hs, as_ = strength.get(home, 40), strength.get(away, 40)
    diff = hs - as_
    if abs(diff) < 8:
        return "draw"
    return "home" if diff > 0 else "away"


def parse_match_date(d: str) -> date:
    day, month = map(int, d.split("/"))
    return date(2026, month, day)


def model_score(home: str, away: str) -> str:
    m = next((x for x in MATCHES if x.home == home and x.away == away), None)
    if not m:
        return "1-1"
    m = _with_odds(m)
    return analyze(m)["score"]


def teams_from_new_results(rows: list[dict], new_keys: set[str]) -> set[str]:
    """Équipes impliquées dans des matchs fraîchement terminés."""
    teams: set[str] = set()
    for row in rows:
        if row["key"] in new_keys:
            teams.add(row["home"])
            teams.add(row["away"])
    return teams


def build_upcoming_updates(
    affected_teams: set[str],
    played_keys: set[str],
    trigger_reason: dict[str, str],
) -> list[dict]:
    """Pronos futurs à revoir : date, équipes, score actuel vs suggéré."""
    today = date.today()
    updates: list[dict] = []

    for m in MATCHES:
        key = match_key(m.home, m.away)
        if key in played_keys:
            continue
        if parse_match_date(m.date) < today:
            continue
        involved = {m.home, m.away} & affected_teams
        if not involved:
            continue

        suggested = model_score(m.home, m.away)
        current = OVERRIDES.get(key, suggested)
        reasons = [trigger_reason.get(t, f"{t} : résultat récent à prendre en compte") for t in sorted(involved)]

        if current == suggested and len(involved) == 0:
            continue

        updates.append({
            "date": m.date,
            "match": key,
            "home": m.home,
            "away": m.away,
            "teams_to_review": sorted(involved),
            "current_score": current,
            "suggested_score": suggested,
            "change": current != suggested,
            "reason": " · ".join(reasons),
        })

    return sorted(updates, key=lambda u: (parse_match_date(u["date"]), u["match"]))


def build_trigger_reasons(rows: list[dict], new_keys: set[str]) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for row in rows:
        if row["key"] not in new_keys:
            continue
        msg = f"{row['key']} terminé {row['actual_score']}"
        if row["user_1n2"] is False:
            msg += " (ton 1/N/2 incorrect)"
        elif row["user_exact"]:
            msg += " (score exact ✓)"
        for team in (row["home"], row["away"]):
            reasons[team] = msg
    return reasons


def model_predict(home: str, away: str) -> str:
    score = OVERRIDES.get(f"{home} - {away}", model_score(home, away))
    return score_outcome(score)


def build_alerts(rows: list[dict], klement: dict) -> list[dict]:
    alerts: list[dict] = []
    user_wrong_streak = 0

    for row in rows:
        if row["user_1n2"] is False:
            user_wrong_streak += 1
        else:
            user_wrong_streak = 0

        if row["user_1n2"] is False and row["actual_outcome"] != "draw":
            winner = row["home"] if row["actual_outcome"] == "home" else row["away"]
            loser = row["away"] if row["actual_outcome"] == "home" else row["home"]
            if winner in HEAVY_FAVORITES and row["user_outcome"] != row["actual_outcome"]:
                if loser in HEAVY_FAVORITES or winner in HEAVY_FAVORITES:
                    pass
            if loser in HEAVY_FAVORITES and row["user_outcome"] != row["actual_outcome"]:
                alerts.append({
                    "level": "warning",
                    "match": row["key"],
                    "message": f"Favori {loser} n'a pas gagné comme prévu ({row['actual_score']})",
                    "action": "Revoir les pronos restants impliquant cette équipe",
                })

        if row.get("klement_1n2") is False and (row["home"] == "Brésil" or row["away"] == "Brésil"):
            if row["actual_outcome"] == "home" and row["home"] == "Brésil":
                alerts.append({
                    "level": "info",
                    "match": row["key"],
                    "message": "Klement prédisait l'élimination du Brésil au 1er tour knockout — trajectoire NL compromise",
                    "action": "Le modèle macro de Klement diverge de la réalité",
                })
            if row["actual_outcome"] == "away" and row["away"] == "Brésil":
                alerts.append({
                    "level": "info",
                    "match": row["key"],
                    "message": "Brésil gagne — Klement avait prévu Japon > Brésil en R32",
                    "action": "Trajectoire Pays-Bas champion Klement moins probable",
                })

        if row["user_score"] is None:
            alerts.append({
                "level": "warning",
                "match": row["key"],
                "message": f"Match joué sans prono dans ta grille ({row['actual_score']})",
                "action": "Compléter sur mpp.football pour les prochains matchs",
            })

    if user_wrong_streak >= 3:
        alerts.append({
            "level": "warning",
            "match": "—",
            "message": f"{user_wrong_streak} derniers pronos 1/N/2 incorrects d'affilée",
            "action": "Envisager d'ajuster la stratégie sur les matchs serrés (plus de nuls ?)",
        })

    winner_pick = "France"  # utilisateur MPP — pourrait lire depuis config
    klement_winner = klement.get("winner", "Pays-Bas")
    if winner_pick != klement_winner:
        user_wins = sum(1 for r in rows if r["user_1n2"])
        klement_wins = sum(1 for r in rows if r.get("klement_1n2"))
        if klement_wins > user_wins + 2 and len(rows) >= 5:
            alerts.append({
                "level": "info",
                "match": "—",
                "message": f"Klement ({klement_wins}/{len(rows)} 1N/2) devance ta grille ({user_wins}/{len(rows)})",
                "action": f"Réfléchir à passer vainqueur MPP sur {klement_winner} ? (optionnel)",
            })

    # dédupliquer alertes identiques
    seen = set()
    unique = []
    for a in alerts:
        k = (a["level"], a["message"])
        if k not in seen:
            seen.add(k)
            unique.append(a)
    return unique


def run_tracker(state: dict | None = None) -> dict:
    state = state or {}
    klement = load_klement()
    finished = fetch_finished_since()
    rows = []

    for m in finished:
        home_fr = to_french(m["home"])
        away_fr = to_french(m["away"])
        key = match_key(home_fr, away_fr)
        act = actual_score(m)
        act_o = outcome(int(m["home_goals"]), int(m["away_goals"]))

        user_score = OVERRIDES.get(key)
        user_o = score_outcome(user_score) if user_score else None
        model_o = model_predict(home_fr, away_fr)
        klement_o = klement_predict(key, home_fr, away_fr, klement)

        rows.append({
            "key": key,
            "home": home_fr,
            "away": away_fr,
            "actual_score": act,
            "actual_outcome": act_o,
            "user_score": user_score,
            "user_outcome": user_o,
            "user_1n2": user_o == act_o if user_o else None,
            "user_exact": user_score == act if user_score else False,
            "model_outcome": model_o,
            "model_1n2": model_o == act_o,
            "klement_outcome": klement_o,
            "klement_1n2": klement_o == act_o if klement_o else None,
        })

    prev_keys = set(state.get("finished_keys", []))
    current_keys = {r["key"] for r in rows}
    new_keys = current_keys - prev_keys

    trigger_reasons = build_trigger_reasons(rows, new_keys)
    affected_teams = teams_from_new_results(rows, new_keys)
    upcoming_updates = (
        build_upcoming_updates(affected_teams, current_keys, trigger_reasons)
        if new_keys
        else []
    )
    recent_results = [r for r in rows if r["key"] in new_keys]

    n = len(rows)
    stats = {
        "played": n,
        "user_1n2": sum(1 for r in rows if r["user_1n2"]),
        "user_exact": sum(1 for r in rows if r["user_exact"]),
        "model_1n2": sum(1 for r in rows if r["model_1n2"]),
        "klement_1n2": sum(1 for r in rows if r.get("klement_1n2")),
    }
    for k in ("user_1n2", "model_1n2", "klement_1n2", "user_exact"):
        stats[f"{k}_pct"] = round(100 * stats[k] / n, 1) if n else 0

    alerts = build_alerts(rows, klement)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "leader_1n2": max(
            [("toi", stats["user_1n2"]), ("modèle", stats["model_1n2"]), ("klement", stats["klement_1n2"])],
            key=lambda x: x[1],
        )[0],
        "mpp_winner_pick": "France",
        "klement_winner_pick": klement.get("winner"),
        "alerts": alerts,
        "matches": rows,
        "new_finished_keys": sorted(new_keys),
        "recent_results": recent_results,
        "upcoming_updates": upcoming_updates,
    }
    return payload


def send_webhook(url: str, payload: dict) -> None:
    alerts = payload.get("alerts", [])
    if not alerts:
        return
    text = "⚽ *MPP Live Tracker*\n"
    text += f"Matchs joués: {payload['stats']['played']} | Toi {payload['stats']['user_1n2_pct']}% 1N/2\n"
    for a in alerts[:5]:
        text += f"\n*{a['level'].upper()}* — {a['message']}\n→ {a['action']}"
    data = json.dumps({"text": text}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook", help="URL Slack/n8n pour alertes")
    parser.add_argument("--email", action="store_true", help="Forcer envoi email")
    parser.add_argument("--dry-run-email", action="store_true", help="Afficher l'email sans envoyer")
    args = parser.parse_args()

    state = load_state()
    payload = run_tracker(state)
    fresh_alerts = new_alerts_only(payload["alerts"], state)
    payload["new_alerts"] = fresh_alerts

    current_keys = {r["key"] for r in payload["matches"]}
    state["finished_keys"] = sorted(current_keys)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    WEB_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if fresh_alerts:
        sent = set(state.get("sent_alerts", []))
        for a in fresh_alerts:
            sent.add(f"{a['level']}|{a['match']}|{a['message']}")
        state["sent_alerts"] = sorted(sent)[-100:]

    s = payload["stats"]
    print("=" * 60)
    print(f"LIVE TRACKER — {s['played']} matchs joués")
    print("=" * 60)
    print(f"  Toi      1N/2: {s['user_1n2']}/{s['played']} ({s['user_1n2_pct']}%) | exact: {s['user_exact']}")
    print(f"  Modèle   1N/2: {s['model_1n2']}/{s['played']} ({s['model_1n2_pct']}%)")
    print(f"  Klement  1N/2: {s['klement_1n2']}/{s['played']} ({s['klement_1n2_pct']}%)")
    print(f"  Leader direction: {payload['leader_1n2']}")

    if payload.get("new_finished_keys"):
        print(f"\n🆕 Nouveaux résultats: {', '.join(payload['new_finished_keys'])}")

    updates = payload.get("upcoming_updates") or []
    if updates:
        print(f"\n📋 {len(updates)} prono(s) à revoir avant match:")
        for u in updates:
            ch = " ← changement" if u["change"] else ""
            print(f"  {u['date']} {u['match']}: {u['current_score']} → {u['suggested_score']}{ch}")
            print(f"       {u['reason']}")

    if payload["alerts"]:
        print(f"\n🔔 {len(payload['alerts'])} alerte(s) ({len(fresh_alerts)} nouvelle(s)):")
        for a in payload["alerts"]:
            tag = " [NEW]" if a in fresh_alerts else ""
            print(f"  [{a['level']}]{tag} {a['message']}")
            print(f"       → {a['action']}")
    else:
        print("\n✅ Aucune alerte")

    print(f"\n→ {OUT}")

    webhook = args.webhook or os.environ.get("MPP_ALERT_WEBHOOK")
    if webhook and fresh_alerts:
        try:
            send_webhook(webhook, {**payload, "alerts": fresh_alerts})
            print("📨 Webhook envoyé (nouvelles alertes uniquement)")
        except Exception as exc:
            print(f"⚠️  Webhook échoué: {exc}")

    should_email = args.email or args.dry_run_email or bool(payload.get("new_finished_keys"))
    email_fp = "|".join(payload.get("new_finished_keys", [])) + "|" + "|".join(
        f"{u['match']}:{u['suggested_score']}" for u in updates
    )
    if should_email and email_fp and email_fp == state.get("last_email_fingerprint"):
        should_email = args.email or args.dry_run_email

    if should_email and (payload.get("new_finished_keys") or args.email or args.dry_run_email):
        try:
            if send_alert_email(payload, dry_run=args.dry_run_email):
                if not args.dry_run_email:
                    state["last_email_fingerprint"] = email_fp
                    print("📧 Email envoyé")
        except Exception as exc:
            print(f"⚠️  Email échoué: {exc}")

    save_state(state)


if __name__ == "__main__":
    main()
