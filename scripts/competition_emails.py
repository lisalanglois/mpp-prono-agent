"""Emails J-7 (préparation compétition) et clôture — multi-compétitions."""

from __future__ import annotations

import json
from pathlib import Path

from alert_email import load_config, recipients, smtp_settings, _mpp_match_card
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import ssl

ROOT = Path(__file__).resolve().parents[1]
sys_path_inserted = False


def _ensure_paths():
    global sys_path_inserted
    if not sys_path_inserted:
        import sys
        sys.path.insert(0, str(ROOT / "src"))
        sys.path.insert(0, str(ROOT / "scripts"))
        sys_path_inserted = True


def _send_raw(subject: str, text: str, html: str) -> bool:
    to_addrs = recipients()
    smtp = smtp_settings()
    if not to_addrs or not smtp:
        return False
    host, port, user, password = smtp
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


def build_pre_competition_payload(comp: dict) -> dict:
    _ensure_paths()
    from mpp.competitions import comp_urls, grid_to_rows, parse_comp_date
    from mpp_recommend import recommend_mpp_score

    klement_path = ROOT / "data" / "klement_predictions.json"
    klement = json.loads(klement_path.read_text()) if klement_path.exists() else {}

    urls = comp_urls(comp)
    rows = []
    for r in grid_to_rows(comp):
        rec = recommend_mpp_score(r["home"], r["away"], klement)
        rows.append({
            **r,
            "score": rec["recommended_score"],
            "score_home": rec["score_home"],
            "score_away": rec["score_away"],
            "klement_override": rec.get("klement_override", False),
        })
    picks = comp.get("mpp_picks", {})
    days = comp.get("days_until_start", "?")

    return {
        "competition": comp,
        "days_until_start": days,
        "start_date": comp["start"],
        "urls": urls,
        "grid_rows": rows,
        "picks": picks,
        "grid_ready": bool(comp.get("grid_module")),
        "note": comp.get("note", ""),
    }


def format_pre_comp_text(p: dict) -> str:
    comp = p["competition"]
    cfg = load_config()
    user = cfg.get("user_label", "Lisa")
    lines = [
        f"⚽ {comp['name']} — J-{p['days_until_start']} avant le coup d'envoi",
        "",
        f"La compétition commence le {p['start_date']}.",
        f"Remplis ta grille sur mpp.football avant le premier match !",
        "",
        "── LIENS ──",
        f"MPP (saisie)     : {p['urls']['mpp']}",
        f"Grille complète  : {p['urls']['grille']}",
        f"Live tracker     : {p['urls']['tracker']}",
        "",
        f"── PRONOS GLOBAUX MPP ({user}) ──",
    ]
    for _key, pick in p["picks"].items():
        if "match" in pick:
            lines.append(f"• {pick['label']} : {pick.get('match')} → {pick.get('score', '—')} ({pick.get('date', '')})")
            if pick.get("note"):
                lines.append(f"  {pick['note']}")
        else:
            lines.append(f"• {pick['label']} : {pick.get('value', '—')}")

    if p["grid_ready"] and p["grid_rows"]:
        lines.append("")
        lines.append(f"── GRILLE COMPLÈTE ({len(p['grid_rows'])} matchs) ──")
        cur_date = None
        for r in p["grid_rows"]:
            if r["date"] != cur_date:
                cur_date = r["date"]
                lines.append(f"\n{cur_date}")
            lines.append(f"  {r['home']} vs {r['away']} → {r['score_home']} - {r['score_away']}")
    elif p.get("note"):
        lines.append("")
        lines.append(f"⚠️ {p['note']}")

    lines += [
        "",
        "── ENSUITE (automatique) ──",
        "• Rappel par email avant chaque match (score exact à mettre)",
        "• Bilan après chaque résultat sur le tracker",
        f"• Dashboard : {p['urls']['tracker']}",
    ]
    return "\n".join(lines)


def format_pre_comp_html(p: dict) -> str:
    comp = p["competition"]
    cfg = load_config()
    user = cfg.get("user_label", "Lisa")

    html = f"""
    <html><body style="font-family:-apple-system,sans-serif;color:#222;max-width:600px;margin:0 auto;padding:16px;">
    <h2>⚽ {comp['name']}</h2>
    <p style="font-size:18px;color:#856404;background:#fff3cd;padding:12px;border-radius:8px;">
      <strong>J-{p['days_until_start']}</strong> — la compétition commence le <strong>{p['start_date']}</strong>
    </p>
    <p>Remplis <strong>toute ta grille</strong> sur Mon Petit Prono avant le premier match.</p>
    <p style="text-align:center;margin:20px 0;">
      <a href="{p['urls']['mpp']}" style="background:#1d9bf0;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;">Ouvrir mpp.football</a>
    </p>
    <p style="text-align:center;font-size:14px;">
      <a href="{p['urls']['grille']}">Grille complète (site)</a> ·
      <a href="{p['urls']['tracker']}">Live tracker</a>
    </p>
    <h3>📌 Pronos globaux MPP ({user})</h3>
    <table width="100%" cellpadding="8" style="font-size:14px;border-collapse:collapse;">
    """

    for _key, pick in p["picks"].items():
        val = pick.get("value") or f"{pick.get('match', '')} → {pick.get('score', '')}"
        html += f"<tr style='border-bottom:1px solid #eee;'><td><strong>{pick['label']}</strong></td><td>{val}</td></tr>"

    html += "</table>"

    if p["grid_ready"] and p["grid_rows"]:
        html += f"<h3>📋 Grille à recopier ({len(p['grid_rows'])} matchs)</h3>"
        html += "<p style='font-size:13px;color:#666;'>Scores suggérés — modifiables sur MPP :</p>"
        cur_date = None
        for r in p["grid_rows"]:
            if r["date"] != cur_date:
                cur_date = r["date"]
                html += f"<h4 style='margin:16px 0 8px;color:#666;'>{cur_date}</h4>"
            html += _mpp_match_card(
                r["home"], r["away"], r["score_home"], r["score_away"],
                subtitle=f"mpp.football → {r['home']} vs {r['away']}",
            )
    else:
        html += f"<p style='color:#856404;background:#fff3cd;padding:12px;border-radius:8px;'>{p.get('note', 'Grille pas encore disponible — reviens sur le site plus tard.')}</p>"

    html += f"""
    <h3>🔔 Ensuite (automatique)</h3>
    <ul style="font-size:14px;">
      <li>Email <strong>avant chaque match</strong> avec le score exact à saisir</li>
      <li>Bilan Lisa vs Klement après chaque résultat</li>
      <li>Suivi live : <a href="{p['urls']['tracker']}">{p['urls']['tracker']}</a></li>
    </ul>
    </body></html>
    """
    return html


def send_pre_competition_email(comp: dict, *, dry_run: bool = False) -> bool:
    payload = build_pre_competition_payload(comp)
    subject = f"⚽ J-{payload['days_until_start']} {comp['short']} — grille MPP à remplir"
    text = format_pre_comp_text(payload)
    html = format_pre_comp_html(payload)
    if dry_run:
        print(f"[pre-comp email] {subject}")
        print(text[:1500])
        return True
    return _send_raw(subject, text, html)


def send_closing_email(comp: dict, tracker: dict | None = None, *, dry_run: bool = False) -> bool:
    _ensure_paths()
    from mpp.competitions import comp_urls

    urls = comp_urls(comp)
    cfg = load_config()
    user = cfg.get("user_label", "Lisa")
    s = (tracker or {}).get("stats", {})

    subject = f"🏁 {comp['short']} terminée — bilan final MPP"
    text = (
        f"{comp['name']} est terminée.\n\n"
        f"Bilan direction {user} : {s.get('user_1n2', '?')}/{s.get('played', '?')}\n"
        f"Scores exacts {user} : {s.get('user_exact', '?')}/{s.get('played', '?')}\n"
        f"Klement : {s.get('klement_1n2', '?')}/{s.get('played', '?')}\n\n"
        f"Classement officiel → {urls['mpp']}\n"
        f"Bilan détaillé → {urls['tracker']}\n"
    )
    html = f"""
    <html><body style="font-family:sans-serif;max-width:560px;margin:0 auto;padding:16px;">
    <h2>🏁 {comp['name']} — terminée</h2>
    <p>Consulte ton classement sur <a href="{urls['mpp']}">mpp.football</a>.</p>
    <h3>Bilan pronos ({user})</h3>
    <ul>
      <li>Direction 1/N/2 : <strong>{s.get('user_1n2', '?')}/{s.get('played', '?')}</strong></li>
      <li>Scores exacts : <strong>{s.get('user_exact', '?')}/{s.get('played', '?')}</strong></li>
      <li>Klement direction : <strong>{s.get('klement_1n2', '?')}/{s.get('played', '?')}</strong></li>
    </ul>
    <p><a href="{urls['tracker']}">Voir le bilan complet</a></p>
    </body></html>
    """
    if dry_run:
        print(f"[closing email] {subject}")
        print(text)
        return True
    return _send_raw(subject, text, html)
