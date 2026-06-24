#!/usr/bin/env python3
"""Envoie l'email récap des scores MPP à mettre à jour après application V2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from alert_email import (  # noqa: E402
    _mpp_match_card,
    load_config,
    recipients,
    smtp_settings,
)
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

CHANGES_PATH = ROOT / "data" / "v2_grille_changes.json"


def build_email(payload: dict) -> tuple[str, str, str]:
    cfg = load_config()
    changes = payload.get("changes") or []
    all_up = payload.get("all_upcoming") or []

    subject = f"⚽ MPP V2 — {len(changes)} score(s) à mettre à jour sur mpp.football"

    text_lines = [
        "⚽ Mon Petit Prono — mise à jour grille V2 (CDM 2026)",
        f"Appliquée le : {payload.get('applied_at', '')[:19].replace('T', ' ')} UTC",
        "",
        "Stratégie V2 : plus de nuls sur matchs équilibrés, moins de 2-0 automatiques,",
        "1/N/2 ancré sur le modèle Poisson (+ ajustement nuls CDM 2026).",
        "",
        f"── {len(changes)} MODIFICATION(S) À FAIRE SUR mpp.football ──",
    ]
    for c in changes:
        old = c.get("old_score") or "—"
        text_lines.append(f"\n📅 {c.get('date', '')} — {c['home']} vs {c['away']}")
        text_lines.append(f"   Ancien : {old}")
        text_lines.append(f"   → METS : {c['new_score'].replace('-', ' - ')}")
        text_lines.append(f"   ({c.get('mpp_instruction', '')})")

    if not changes:
        text_lines.append("(Aucun changement — grille déjà alignée V2)")

    text_lines += ["", "── TOUS LES MATCHS RESTANTS (référence) ──"]
    for c in sorted(all_up, key=lambda x: (x.get("date", ""), x["key"])):
        mark = "*" if c in changes else " "
        text_lines.append(
            f"{mark} {c.get('date','')} {c['home']} vs {c['away']} → {c['new_score']}"
        )

    text_lines += [
        "",
        f"Ouvrir : {cfg.get('mpp_url', 'https://mpp.football')}",
        "Dashboard : https://lisalanglois.github.io/mpp-prono-agent/tracker.html",
    ]
    text_body = "\n".join(text_lines)

    html = f"""
    <html><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#222;max-width:560px;margin:0 auto;padding:12px;">
    <h2 style="margin:0;">⚽ MPP — Grille V2 à jour</h2>
    <p style="color:#666;font-size:13px;">{payload.get('applied_at', '')[:19].replace('T', ' ')} UTC</p>
    <div style="background:#e8f4fd;border-radius:8px;padding:14px;font-size:14px;color:#333;margin:16px 0;">
      <strong>Stratégie V2</strong> (après analyse J1–J2) :<br>
      • Plus de <strong>nuls</strong> sur matchs équilibrés (~29 % observés)<br>
      • Moins de <strong>2-0</strong> systématiques sur les favoris<br>
      • <strong>1/N/2</strong> guidé par le modèle Poisson + boost nuls CDM
    </div>
    """

    if changes:
        html += f"""
        <div style="background:#fff3cd;border:2px solid #c9a227;border-radius:12px;padding:16px;margin:20px 0;">
          <h3 style="margin:0 0 12px;color:#856404;">🔁 {len(changes)} score(s) à modifier sur mpp.football</h3>
        """
        for c in changes:
            nh, na = c["new_score"].split("-")
            old = c.get("old_score")
            oh, oa = (None, None)
            if old and old not in ("(nouveau)", "—", None) and "-" in str(old):
                oh, oa = old.split("-")
            html += _mpp_match_card(
                c["home"],
                c["away"],
                nh.strip(),
                na.strip(),
                date=f"<strong>{c.get('date', '')}</strong> · tier {c.get('tier', '?')} · P(nul) {int((c.get('p_draw') or 0)*100)}%",
                subtitle=c.get("mpp_instruction", ""),
                old_h=oh,
                old_a=oa,
                highlight=True,
            )
        html += "</div>"
    else:
        html += "<p>Aucun changement par rapport à la grille précédente.</p>"

    html += "<h3 style='margin-top:24px;'>📋 Tous les matchs restants</h3>"
    for c in sorted(all_up, key=lambda x: (x.get("date", ""), x["key"])):
        h, a = c["new_score"].split("-")
        changed = c in changes
        html += _mpp_match_card(
            c["home"],
            c["away"],
            h.strip(),
            a.strip(),
            date=f"{c.get('date', '')}{' · modifié' if changed else ''}",
            highlight=changed,
        )

    html += f"""
    <p style="margin-top:24px;font-size:13px;color:#888;text-align:center;">
      <a href="{cfg.get('mpp_url', 'https://mpp.football')}">Ouvrir mpp.football</a>
    </p>
    </body></html>
    """
    return subject, text_body, html


def send(*, dry_run: bool = False) -> bool:
    if not CHANGES_PATH.exists():
        print(f"❌ Fichier absent : {CHANGES_PATH} — lancer apply_v2_grille.py d'abord")
        return False

    payload = json.loads(CHANGES_PATH.read_text(encoding="utf-8"))
    to_addrs = recipients()
    if not to_addrs:
        print("⚠️  Aucun destinataire")
        return False

    subject, text, html = build_email(payload)

    if dry_run:
        print(f"[dry-run] To: {', '.join(to_addrs)}")
        print(f"Subject: {subject}")
        print("-" * 40)
        print(text)
        return True

    smtp = smtp_settings()
    if not smtp:
        print("⚠️  SMTP non configuré — lancer avec : set -a && source .env && set +a")
        print("-" * 40)
        print(text)
        return False

    host, port, user, password = smtp
    cfg = load_config()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{cfg.get('sender_name', 'MPP')} <{user}>"
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=ctx)
        server.login(user, password)
        server.sendmail(user, to_addrs, msg.as_string())
    print(f"📧 Email V2 envoyé à {', '.join(to_addrs)}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    ok = send(dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
