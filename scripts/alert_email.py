"""Envoi d'alertes email (SMTP) pour le live tracker MPP — format lisible + style MPP."""

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

# Styles inline pour clients mail
BOX = (
    "background:#152a22;border:2px solid #1a5c3a;border-radius:12px;"
    "padding:16px;margin:16px 0;"
)
BOX_CHANGE = (
    "background:#2a2010;border:2px solid #c9a227;border-radius:12px;"
    "padding:16px;margin:16px 0;"
)
SCORE = (
    "display:inline-block;width:44px;height:44px;line-height:44px;"
    "background:#0f1419;border:2px solid #1d9bf0;border-radius:8px;"
    "font-size:22px;font-weight:bold;text-align:center;color:#fff;"
)
SCORE_OLD = (
    "display:inline-block;width:44px;height:44px;line-height:44px;"
    "background:#0f1419;border:2px dashed #666;border-radius:8px;"
    "font-size:22px;font-weight:bold;text-align:center;color:#999;"
    "text-decoration:line-through;"
)


def load_config() -> dict:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    return {
        "recipients": [],
        "mpp_winner_pick": "France",
        "sender_name": "MPP Prono Agent",
        "user_label": "Lisa",
        "mpp_url": "https://mpp.football",
        "klement_blurb": "",
    }


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


def _score_box(h: str, a: str, *, old: bool = False) -> str:
    style = SCORE_OLD if old else SCORE
    return f'<span style="{style}">{h}</span> : <span style="{style}">{a}</span>'


def _mpp_match_card(
    home: str,
    away: str,
    h: str,
    a: str,
    *,
    date: str = "",
    subtitle: str = "",
    old_h: str | None = None,
    old_a: str | None = None,
    highlight: bool = False,
) -> str:
    box = BOX_CHANGE if highlight else BOX
    date_line = f'<div style="text-align:center;color:#7dd3a0;font-size:13px;margin-bottom:8px;">{date}</div>' if date else ""
    sub = f'<div style="text-align:center;color:#888;font-size:12px;margin-top:10px;">{subtitle}</div>' if subtitle else ""
    old_line = ""
    if old_h is not None and old_a is not None and (old_h != h or old_a != a):
        old_line = (
            f'<div style="text-align:center;color:#999;font-size:12px;margin-bottom:6px;">'
            f'Ancien prono : {_score_box(old_h, old_a, old=True)}</div>'
        )
    return f"""
    <div style="{box}">
      {date_line}
      <table width="100%" cellpadding="4"><tr>
        <td align="right" style="font-weight:bold;font-size:15px;">{home}</td>
        <td align="center" width="120">{old_line}{_score_box(h, a)}</td>
        <td align="left" style="font-weight:bold;font-size:15px;">{away}</td>
      </tr></table>
      {sub}
    </div>
    """


def _intro_html(cfg: dict) -> str:
    user = cfg.get("user_label", "Lisa")
    klement = cfg.get("klement_blurb", "")
    mpp = cfg.get("mpp_url", "https://mpp.football")
    return f"""
    <div style="background:#f5f5f5;border-radius:8px;padding:14px;margin:16px 0;font-size:14px;color:#444;">
      <strong>C'est quoi ce mail ?</strong><br>
      On joue à <a href="{mpp}">Mon Petit Prono (mpp.football)</a> entre amis sur la Coupe du Monde 2026.<br><br>
      <strong>{user}</strong> = les scores que tu as (ou devais) mettre sur MPP.<br>
      <strong>Klement</strong> = {klement}<br>
      <strong>1/N/2</strong> = qui gagne ou match nul (le score exact est un bonus).
    </div>
    """


def format_email_html(payload: dict) -> str:
    s = payload["stats"]
    cfg = load_config()
    user = cfg.get("user_label", "Lisa")

    html = f"""
    <html><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#222;max-width:560px;margin:0 auto;padding:12px;">
    <h2 style="margin:0;">⚽ Mon Petit Prono — CDM 2026</h2>
    <p style="color:#666;font-size:13px;">{payload.get('updated_at', '')[:19].replace('T', ' ')} UTC</p>
    """
    html += _intro_html(cfg)

    recent = payload.get("recent_results") or []
    if recent:
        html += f"<h3 style='margin-top:24px;'>🏁 Dernier(s) match(s) terminé(s)</h3>"
        for r in recent:
            html += f"""
            <p style="font-size:15px;margin:8px 0;"><strong>{r['home']} vs {r['away']}</strong></p>
            """
            html += _mpp_match_card(
                r["home"], r["away"],
                r.get("actual_home", "—"), r.get("actual_away", "—"),
                subtitle="↑ Résultat réel",
            )
            html += f"""
            <table width="100%" style="font-size:14px;margin:8px 0;" cellpadding="4">
              <tr><td><strong>{user}</strong> avait prédit</td>
                  <td><strong>{r.get('user_score') or '—'}</strong> ({r.get('user_direction', '—')})</td>
                  <td>{'✅' if r.get('user_1n2') else '❌' if r.get('user_1n2') is False else '—'}</td></tr>
              <tr><td><strong>Klement</strong> avait prédit</td>
                  <td>{r.get('klement_direction', '—')}</td>
                  <td>{'✅' if r.get('klement_1n2') else '❌' if r.get('klement_1n2') is False else '—'}</td></tr>
            </table>
            <div style="background:#e8f5e9;border-radius:8px;padding:12px;font-size:15px;font-weight:bold;text-align:center;">
              {r.get('verdict_short', '')}
            </div>
            """

    # Bilan global
    html += f"""
    <h3 style="margin-top:24px;">📊 Bilan direction (1/N/2)</h3>
    <table width="100%" style="font-size:14px;" cellpadding="6">
      <tr style="background:#eee;"><th></th><th>Correct</th><th>%</th></tr>
      <tr><td><strong>{user}</strong></td><td>{s['user_1n2']}/{s['played']}</td><td>{s['user_1n2_pct']}%</td></tr>
      <tr><td>Modèle IA</td><td>{s['model_1n2']}/{s['played']}</td><td>{s['model_1n2_pct']}%</td></tr>
      <tr><td>Klement</td><td>{s['klement_1n2']}/{s['played']}</td><td>{s['klement_1n2_pct']}%</td></tr>
    </table>
    <p style="font-size:13px;color:#666;">
      Vainqueur MPP : <strong>{cfg.get('mpp_winner_pick', payload.get('mpp_winner_pick'))}</strong> ·
      Klement avait : <strong>{payload.get('klement_winner_pick', '—')}</strong>
    </p>
    """

    updates = payload.get("upcoming_updates") or []
    if updates:
        html += "<h3 style='margin-top:24px;'>📋 À mettre sur mpp.football (avant le match)</h3>"
        html += "<p style='font-size:13px;color:#666;'>Recopie ces scores dans l'app — cases comme ci-dessous :</p>"
        for u in updates:
            html += _mpp_match_card(
                u["home"], u["away"],
                u.get("suggested_home", "—"), u.get("suggested_away", "—"),
                date=f"{u['date']} — match à venir",
                subtitle=u.get("mpp_action", u.get("reason", "")),
                old_h=u.get("current_home") if u.get("change") else None,
                old_a=u.get("current_away") if u.get("change") else None,
                highlight=u.get("change", False),
            )

    alerts = payload.get("new_alerts") or payload.get("alerts") or []
    if alerts:
        html += "<h3>🔔 Points d'attention</h3><ul style='font-size:14px;'>"
        for a in alerts:
            html += f"<li><strong>{a['message']}</strong><br><span style='color:#666;'>{a['action']}</span></li>"
        html += "</ul>"

    html += f"""
    <p style="margin-top:24px;font-size:13px;color:#888;text-align:center;">
      <a href="{cfg.get('mpp_url', 'https://mpp.football')}">Ouvrir mpp.football</a> ·
      <a href="https://lisalanglois.github.io/mpp-prono-agent/tracker.html">Dashboard complet</a>
    </p>
    </body></html>
    """
    return html


def format_email_text(payload: dict) -> str:
    cfg = load_config()
    user = cfg.get("user_label", "Lisa")
    s = payload["stats"]
    lines = [
        "⚽ Mon Petit Prono — CDM 2026",
        f"Mis à jour : {payload.get('updated_at', '')[:19]} UTC",
        "",
        "── C'EST QUOI ? ──",
        f"Jeu Mon Petit Prono (mpp.football) entre amis.",
        f"{user} = ta grille · Klement = économiste (modèle macro, Pays-Bas champion).",
        "1/N/2 = qui gagne ou nul. Score exact = bonus.",
        "",
    ]

    recent = payload.get("recent_results") or []
    if recent:
        lines.append("── DERNIER(S) MATCH(S) ──")
        for r in recent:
            lines.append(f"\n{r['home']} vs {r['away']} → RÉSULTAT {r['actual_score']}")
            lines.append(f"  {user} : {r.get('user_score') or '—'} ({r.get('user_direction')}) {'✓' if r.get('user_1n2') else '✗'}")
            lines.append(f"  Klement : {r.get('klement_direction')} {'✓' if r.get('klement_1n2') else '✗'}")
            lines.append(f"  ▶ {r.get('verdict_short')}")
        lines.append("")

    lines += [
        "── BILAN DIRECTION ──",
        f"{user} : {s['user_1n2']}/{s['played']} ({s['user_1n2_pct']}%)",
        f"Modèle : {s['model_1n2_pct']}% · Klement : {s['klement_1n2_pct']}%",
        "",
    ]

    updates = payload.get("upcoming_updates") or []
    if updates:
        lines.append("── À METTRE SUR mpp.football ──")
        for u in updates:
            lines.append(f"\n📅 {u['date']} — {u['home']} vs {u['away']}")
            if u.get("change"):
                lines.append(f"   Remplace {u['current_score']} par → {u['suggested_score']}")
            else:
                lines.append(f"   Garde → {u['suggested_score']}")
            lines.append(f"   {u.get('mpp_action', u.get('reason', ''))}")
        lines.append("")

    alerts = payload.get("new_alerts") or payload.get("alerts") or []
    if alerts:
        lines.append("── ALERTES ──")
        for a in alerts:
            lines.append(f"• {a['message']} → {a['action']}")
        lines.append("")

    lines.append(f"mpp.football : {cfg.get('mpp_url', 'https://mpp.football')}")
    return "\n".join(lines)


def email_subject(payload: dict) -> str:
    recent = payload.get("recent_results") or []
    if recent:
        r = recent[-1]
        return f"⚽ {r['home']} {r['actual_score']} {r['away']} — {r.get('verdict_short', 'résultat')}"
    n = len(payload.get("upcoming_updates") or [])
    if n:
        return f"⚽ MPP — {n} score(s) à mettre à jour sur mpp.football"
    return f"⚽ MPP CDM — bilan ({payload.get('stats', {}).get('played', 0)} matchs)"


def send_alert_email(payload: dict, *, dry_run: bool = False) -> bool:
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
