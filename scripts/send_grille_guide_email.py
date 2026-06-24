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


def build_html(guide: dict) -> str:
    cfg = load_config()
    html = f"""
    <html><body style="font-family:-apple-system,sans-serif;color:#222;max-width:560px;margin:0 auto;padding:12px;">
    <h2>⚽ MPP — Guide grille V3</h2>
    <p style="color:#666;font-size:13px;">{guide['generated_at'][:19].replace('T', ' ')} UTC</p>
    <div style="background:#e8f4fd;border-radius:8px;padding:14px;font-size:14px;margin:16px 0;">
      <strong>1/N/2</strong> : foule MPP → cotes ESPN → Klement<br>
      <strong>Score exact</strong> : Poisson (calibré foule/cotes)<br>
      <strong>Nul</strong> : seulement si foule nul élevée sans favori &gt; 55 %
    </div>
    """

    s = guide["summary"]
    html += f"<p><strong>{s['to_change']} à modifier</strong> · {s['to_set']} à saisir · {s['ok']} OK · {s['review']} à vérifier</p>"

    if guide["to_change"]:
        html += '<div style="background:#fff3cd;border:2px solid #c9a227;border-radius:12px;padding:16px;margin:20px 0;">'
        html += f"<h3>🔁 {len(guide['to_change'])} score(s) à modifier</h3>"
        for r in guide["to_change"]:
            nh, na = r["recommended_score"].split("-")
            oh, oa = (None, None)
            if r.get("user_score") and "-" in r["user_score"]:
                oh, oa = r["user_score"].split("-")
            html += _mpp_match_card(
                r["home"], r["away"], nh.strip(), na.strip(),
                date=f"<strong>{r['date']}</strong> · {r['reason']} · foule {r['crowd']}%",
                subtitle=r["mpp_instruction"],
                old_h=oh, old_a=oa, highlight=True,
            )
        html += "</div>"

    if guide["to_set"]:
        html += "<h3>➕ À saisir</h3>"
        for r in guide["to_set"]:
            h, a = r["recommended_score"].split("-")
            html += _mpp_match_card(
                r["home"], r["away"], h.strip(), a.strip(),
                date=f"{r['date']} · {r['reason']}",
                subtitle=r["mpp_instruction"],
            )

    if guide["review"]:
        html += '<div style="background:#f8f9fa;border-radius:8px;padding:12px;margin:16px 0;">'
        html += f"<h3>⚠️ {len(guide['review'])} match(s) serrés</h3><ul>"
        for r in guide["review"]:
            cur = r.get("user_score") or "—"
            html += f"<li>{r['date']} {r['home']} vs {r['away']} — suggéré <strong>{r['recommended_score']}</strong> (actuel {cur})</li>"
        html += "</ul></div>"

    html += f'<p style="text-align:center;"><a href="{cfg.get("mpp_url", "https://mpp.football")}">mpp.football</a></p></body></html>'
    return html


def send(*, dry_run: bool = False) -> bool:
    guide = build_guide()
    GUIDE_PATH.write_text(json.dumps(guide, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    to_addrs = recipients()
    if not to_addrs:
        print("⚠️  Aucun destinataire")
        return False

    s = guide["summary"]
    subject = f"⚽ MPP V3 — {s['to_change']} modif + {s['to_set']} à saisir (guide fiable)"
    text = format_text(guide)
    html = build_html(guide)

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
