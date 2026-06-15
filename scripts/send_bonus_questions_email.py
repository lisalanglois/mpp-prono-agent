#!/usr/bin/env python3
"""Envoie les réponses aux questions bonus MPP (vainqueur, buteur, trajectoire France)."""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPETITIONS = ROOT / "data" / "competitions.json"
DAILY = ROOT / "data" / "daily_predictions.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _smtp() -> tuple[str, int, str, str] | None:
    user = os.environ.get("MPP_SMTP_USER", "").strip()
    password = os.environ.get("MPP_SMTP_PASSWORD", "").strip()
    if not user or not password:
        return None
    host = os.environ.get("MPP_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("MPP_SMTP_PORT", "587"))
    return host, port, user, password


def _recipients(cli_to: str | None) -> list[str]:
    if cli_to:
        return [e.strip() for e in cli_to.split(",") if e.strip()]
    env = os.environ.get("MPP_ALERT_EMAILS", "")
    if env.strip():
        return [e.strip() for e in env.split(",") if e.strip()]
    from alert_email import load_config

    return load_config().get("recipients", [])


def build_content() -> tuple[str, str, str]:
    comp = next(c for c in _load_json(COMPETITIONS)["competitions"] if c["id"] == "cdm2026")
    picks = comp["mpp_picks"]
    winner = picks["winner"]["value"]
    scorer = picks["top_scorer"]["value"]
    france_path = "Championne du monde" if winner == "France" else "Finale"

    upcoming = []
    if DAILY.exists():
        for p in _load_json(DAILY).get("predictions", [])[:5]:
            upcoming.append(f"• {p['match']} → {p['score']}")

    subject = "⚽ MPP CDM 2026 — réponses questions bonus (En cours)"

    text = f"""Bonjour Juliette,

Voici les réponses à saisir dans l'onglet « En cours » sur mpp.football, alignées sur nos derniers pronos MPP (grille Lisa + agent).

⚠️ Estimations probabilistes — pas des certitudes. Confiance : modérée.

── QUESTIONS BONUS (deadline 11 juin 20h) ──

1) Quelle nation sera championne du monde ?
   → {winner}
   (cohérent avec notre vainqueur MPP et la grille : France favorite, bonus x2 sur France–Sénégal 2-0)

2) Quel joueur sera le meilleur buteur ?
   → {scorer}
   (France championne → attaquant français le plus probable)

3) Jusqu'où ira l'équipe de France ?
   → {france_path}
   (doit être cohérent avec la réponse vainqueur : si France championne, choisir « Championne du monde »)

── PROCHAINS MATCHS (grille récente) ──
{chr(10).join(upcoming) if upcoming else "—"}

── RAPPEL ──
• Espagne – Cap-Vert : 2-0
• Belgique – Égypte : 2-0
• Arabie saoudite – Uruguay : 0-1

mpp.football : https://mpp.football
Tracker : https://lisalanglois.github.io/mpp-prono-agent/tracker.html

Bons pronos !
— MPP Prono Agent (Lisa)
"""

    html = f"""
<html><body style="font-family:-apple-system,sans-serif;color:#222;max-width:600px;margin:0 auto;padding:16px;">
<h2>⚽ MPP CDM 2026 — questions bonus</h2>
<p style="background:#fff3cd;padding:12px;border-radius:8px;font-size:14px;">
  <strong>⚠️ Estimations probabilistes</strong> — confiance modérée. À recopier dans l'onglet <em>En cours</em> sur mpp.football.
</p>
<table width="100%" cellpadding="10" style="border-collapse:collapse;font-size:15px;">
<tr style="background:#f5f5f5;"><td><strong>Championne du monde</strong></td><td><strong>{winner}</strong></td></tr>
<tr><td><strong>Meilleur buteur</strong></td><td><strong>{scorer}</strong></td></tr>
<tr style="background:#f5f5f5;"><td><strong>Jusqu'où ira la France ?</strong></td><td><strong>{france_path}</strong></td></tr>
</table>
<h3>Prochains matchs (grille)</h3>
<ul>{''.join(f'<li>{line[2:]}</li>' for line in upcoming)}</ul>
<p><a href="https://mpp.football">Ouvrir mpp.football</a></p>
</body></html>
"""
    return subject, text, html


def send(*, to: str | None = None, dry_run: bool = False) -> bool:
    to_addrs = _recipients(to)
    if not to_addrs:
        print("⚠️  Aucun destinataire")
        return False

    subject, text, html = build_content()
    if dry_run:
        print(f"[dry-run] To: {', '.join(to_addrs)}")
        print(f"Subject: {subject}")
        print(text)
        return True

    smtp = _smtp()
    if not smtp:
        print("⚠️  SMTP non configuré (MPP_SMTP_USER + MPP_SMTP_PASSWORD)")
        return False

    host, port, user, password = smtp
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"MPP Prono Agent <{user}>"
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=ctx)
        server.login(user, password)
        server.sendmail(user, to_addrs, msg.as_string())
    print(f"📧 Email bonus envoyé à {', '.join(to_addrs)}")
    return True


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--to", help="Destinataire(s), séparés par des virgules")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    ok = send(to=args.to, dry_run=args.dry_run)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
