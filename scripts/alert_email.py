"""Envoi d'alertes email (SMTP) pour le live tracker MPP."""

from __future__ import annotations

import json
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data" / "alert_config.json"


def load_config() -> dict:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    return {"recipients": [], "mpp_winner_pick": "France", "sender_name": "MPP Prono Agent"}


def recipients() -> list[str]:
    env = os.environ.get("MPP_ALERT_EMAILS", "")
    if env.strip():
        return [e.strip() for e in env.split(",") if e.strip()]
    return load_config().get("recipients", [])


def smtp_settings() -> tuple[str, int, str, str] | None:
    user = os.environ.get("MPP_SMTP_USER", "").strip()
    password = os.environ.get("MPP_SMTP_PASSWORD", "").strip()
    if not user or not password:
        return None
    host = os.environ.get("MPP_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("MPP_SMTP_PORT", "587"))
    return host, port, user, password


def format_email_html(payload: dict) -> str:
    s = payload["stats"]
    cfg = load_config()
    html = f"""
    <html><body style="font-family:sans-serif;color:#222;max-width:640px;">
    <h2>⚽ MPP CDM 2026 — Live Tracker</h2>
    <p><em>{payload.get('updated_at', '')[:19].replace('T', ' ')} UTC</em></p>
    <p>
      <strong>Stats 1/N/2</strong> — Toi {s['user_1n2']}/{s['played']} ({s['user_1n2_pct']}%) ·
      Modèle {s['model_1n2_pct']}% · Klement {s['klement_1n2_pct']}%<br>
      Vainqueur MPP : <strong>{cfg.get('mpp_winner_pick', payload.get('mpp_winner_pick'))}</strong>
      · Klement : <strong>{payload.get('klement_winner_pick', '—')}</strong>
    </p>
    """

    updates = payload.get("upcoming_updates") or []
    if updates:
        html += "<h3>📋 Pronos à revoir sur mpp.football (avant match)</h3><table border='0' cellpadding='6' style='border-collapse:collapse;width:100%;'>"
        html += "<tr style='background:#eee;'><th>Date</th><th>Match</th><th>Actuel</th><th>Suggéré</th><th>Raison</th></tr>"
        for u in updates:
            html += (
                f"<tr><td><strong>{u['date']}</strong></td>"
                f"<td>{u['match']}</td>"
                f"<td>{u['current_score']}</td>"
                f"<td><strong>{u['suggested_score']}</strong></td>"
                f"<td style='font-size:0.9em;color:#555;'>{u['reason']}</td></tr>"
            )
        html += "</table>"

    recent = payload.get("recent_results") or []
    if recent:
        html += "<h3>🏁 Derniers résultats</h3><ul>"
        for r in recent:
            ok = "✓" if r.get("user_1n2") else "✗" if r.get("user_1n2") is False else "—"
            html += (
                f"<li><strong>{r['key']}</strong> → {r['actual_score']} "
                f"(ton prono : {r.get('user_score') or '—'} {ok})</li>"
            )
        html += "</ul>"

    alerts = payload.get("new_alerts") or payload.get("alerts") or []
    if alerts:
        html += "<h3>🔔 Alertes</h3><ul>"
        for a in alerts:
            html += f"<li><strong>[{a['level']}]</strong> {a['message']}<br><em>→ {a['action']}</em></li>"
        html += "</ul>"

    html += """
    <p style="margin-top:2em;font-size:0.85em;color:#888;">
      Dashboard : <a href="https://lisalanglois.github.io/mpp-prono-agent/tracker.html">tracker.html</a>
    </p>
    </body></html>
    """
    return html


def format_email_text(payload: dict) -> str:
    s = payload["stats"]
    lines = [
        "⚽ MPP CDM 2026 — Live Tracker",
        f"Mis à jour : {payload.get('updated_at', '')[:19]} UTC",
        "",
        f"Stats 1/N/2 — Toi {s['user_1n2']}/{s['played']} ({s['user_1n2_pct']}%)",
        f"Modèle {s['model_1n2_pct']}% · Klement {s['klement_1n2_pct']}%",
        "",
    ]

    updates = payload.get("upcoming_updates") or []
    if updates:
        lines.append("═══ PRONOS À REVOIR (avant match) ═══")
        for u in updates:
            lines.append(f"📅 {u['date']} — {u['match']}")
            lines.append(f"   Actuel {u['current_score']} → Suggéré {u['suggested_score']}")
            lines.append(f"   {u['reason']}")
            lines.append("")

    recent = payload.get("recent_results") or []
    if recent:
        lines.append("═══ DERNIERS RÉSULTATS ═══")
        for r in recent:
            ok = "OK" if r.get("user_1n2") else "KO" if r.get("user_1n2") is False else "—"
            lines.append(
                f"• {r['key']} → {r['actual_score']} (prono {r.get('user_score') or '—'} [{ok}])"
            )
        lines.append("")

    alerts = payload.get("new_alerts") or payload.get("alerts") or []
    if alerts:
        lines.append("═══ ALERTES ═══")
        for a in alerts:
            lines.append(f"[{a['level']}] {a['message']}")
            lines.append(f"  → {a['action']}")
        lines.append("")

    lines.append("Dashboard : https://lisalanglois.github.io/mpp-prono-agent/tracker.html")
    return "\n".join(lines)


def email_subject(payload: dict) -> str:
    n = len(payload.get("upcoming_updates") or [])
    played = payload.get("stats", {}).get("played", 0)
    if n:
        return f"⚽ MPP CDM — {n} prono(s) à revoir avant match"
    if payload.get("new_alerts"):
        return f"⚽ MPP CDM — {len(payload['new_alerts'])} alerte(s) ({played} matchs joués)"
    return f"⚽ MPP CDM — mise à jour ({played} matchs joués)"


def send_alert_email(payload: dict, *, dry_run: bool = False) -> bool:
    """Envoie l'email aux destinataires configurés. Retourne True si envoyé."""
    to_addrs = recipients()
    if not to_addrs:
        print("⚠️  Aucun destinataire email configuré")
        return False

    subject = email_subject(payload)
    text = format_email_text(payload)

    if dry_run:
        print(f"[dry-run email] To: {', '.join(to_addrs)}")
        print(f"Subject: {subject}")
        print("-" * 40)
        print(text)
        return True

    smtp = smtp_settings()
    if not smtp:
        print("⚠️  SMTP non configuré (MPP_SMTP_USER + MPP_SMTP_PASSWORD)")
        return False

    host, port, user, password = smtp
    html = format_email_html(payload)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{load_config().get('sender_name', 'MPP')} <{user}>"
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=ctx)
        server.login(user, password)
        server.sendmail(user, to_addrs, msg.as_string())
    return True
