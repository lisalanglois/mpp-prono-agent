#!/usr/bin/env python3
"""Email guide V3 — uniquement les actions fiables sur mpp.football."""

from __future__ import annotations

import argparse
import json
import smtplib
import ssl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from alert_email import _mpp_match_card, load_config, recipients, smtp_settings  # noqa: E402
from grille_guide import build_guide, format_text  # noqa: E402
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GUIDE_PATH = ROOT / "data" / "grille_guide.json"
CHANGES_PATH = ROOT / "data" / "v3_grille_changes.json"


def _action_rows(guide: dict) -> list[dict]:
    """Actions à faire sur mpp.football (depuis dernier apply V3 si dispo)."""
    if CHANGES_PATH.exists():
        payload = json.loads(CHANGES_PATH.read_text(encoding="utf-8"))
        rows = payload.get("changes") or []
        if rows:
            return rows
    return guide["to_change"] + guide["to_set"]


def build_html(guide: dict, actions: list[dict]) -> str:
    cfg = load_config()
    html = f"""
    <html><body style="font-family:-apple-system,sans-serif;color:#222;max-width:560px;margin:0 auto;padding:12px;">
    <h2>⚽ MPP — Guide grille V3</h2>
    <p style="color:#666;font-size:13px;">{guide['generated_at'][:19].replace('T', ' ')} UTC</p>
    <div style="background:#e8f4fd;border-radius:8px;padding:14px;font-size:14px;margin:16px 0;">
      <strong>1/N/2</strong> : foule MPP → cotes ESPN → Klement<br>
      <strong>Score exact</strong> : Poisson (calibré foule/cotes)<br>
      <strong>Nul</strong> : seulement si foule nul élevée sans favori &gt; 55 %<br>
      <em>Remplace le mail V2 (nuls forcés à tort).</em>
    </div>
    """

    html += f"<p><strong>{len(actions)} action(s)</strong> sur mpp.football · {guide['summary']['ok']} autres matchs OK</p>"

    if actions:
        html += '<div style="background:#fff3cd;border:2px solid #c9a227;border-radius:12px;padding:16px;margin:20px 0;">'
        html += f"<h3>🔁 {len(actions)} score(s) à mettre à jour</h3>"
        for r in actions:
            nh, na = r["new_score"].split("-")
            old = r.get("old_score")
            oh, oa = (None, None)
            if old and old not in ("(nouveau)", "—", None) and "-" in str(old):
                oh, oa = old.split("-")
            reason = r.get("reason") or ""
            crowd = r.get("crowd") or ""
            conf = r.get("confidence") or ""
            html += _mpp_match_card(
                r["home"], r["away"], nh.strip(), na.strip(),
                date=f"<strong>{r.get('date', '')}</strong> · {reason} · foule {crowd}% · {conf}",
                subtitle=r.get("mpp_instruction", ""),
                old_h=oh, old_a=oa, highlight=True,
            )
        html += "</div>"

    if guide["review"]:
        html += '<div style="background:#f8f9fa;border-radius:8px;padding:12px;margin:16px 0;">'
        html += f"<h3>⚠️ {len(guide['review'])} match(s) serrés</h3><ul>"
        for r in guide["review"]:
            cur = r.get("user_score") or "—"
            html += f"<li>{r['date']} {r['home']} vs {r['away']} — suggéré <strong>{r['recommended_score']}</strong> (actuel {cur})</li>"
        html += "</ul></div>"

    html += f'<p style="text-align:center;"><a href="{cfg.get("mpp_url", "https://mpp.football")}">mpp.football</a></p></body></html>'
    return html


def format_actions_text(guide: dict, actions: list[dict]) -> str:
    lines = [
        "⚽ MPP — Guide grille V3 (fiable)",
        f"Généré : {guide['generated_at'][:19].replace('T', ' ')} UTC",
        "",
        "Remplace le mail V2. Logique : foule MPP → cotes → Klement ; Poisson = score exact.",
        "",
        f"═══ {len(actions)} ACTION(S) sur mpp.football ═══",
    ]
    for r in actions:
        old = r.get("old_score") or "—"
        lines.append("")
        lines.append(f"📅 {r.get('date', '')} — {r['home']} vs {r['away']}")
        lines.append(f"   Actuel (V2 / app) : {old}")
        lines.append(f"   → METS : {r['new_score'].replace('-', ' - ')}")
        lines.append(f"   {r.get('reason', '')} | foule {r.get('crowd', '')}% | confiance {r.get('confidence', '')}")
    lines.append("")
    lines.append(f"✅ {guide['summary']['ok']} autres matchs : ne pas toucher")
    lines.append("→ https://mpp.football")
    return "\n".join(lines)


def send(*, dry_run: bool = False) -> bool:
    guide = build_guide()
    GUIDE_PATH.write_text(json.dumps(guide, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    actions = _action_rows(guide)

    to_addrs = recipients()
    if not to_addrs:
        print("⚠️  Aucun destinataire")
        return False

    subject = f"⚽ MPP V3 — {len(actions)} score(s) à mettre sur mpp.football (guide fiable)"
    text = format_actions_text(guide, actions)
    html = build_html(guide, actions)

    if dry_run:
        print(f"[dry-run] To: {', '.join(to_addrs)}")
        print(f"Subject: {subject}")
        print("-" * 40)
        print(text)
        return True

    smtp = smtp_settings()
    if not smtp:
        print("⚠️  SMTP non configuré localement — affichage du guide :")
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
    print(f"📧 Guide V3 envoyé à {', '.join(to_addrs)}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    ok = send(dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
