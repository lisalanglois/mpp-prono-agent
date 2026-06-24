#!/usr/bin/env python3
"""Guide fiable : quoi mettre sur mpp.football, match par match (stratégie V3)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mpp_grille_cdm import MATCHES  # noqa: E402
from mpp_recommend import load_klement, recommend_mpp_score  # noqa: E402

OUT_JSON = ROOT / "data" / "grille_guide.json"


def played_keys() -> set[str]:
    path = ROOT / "data" / "live_tracker.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {m["key"] for m in data.get("matches", []) if m.get("actual_score")}


def build_guide() -> dict:
    played = played_keys()
    klement = load_klement()
    by_date: dict[str, list] = {}
    to_set: list[dict] = []
    to_change: list[dict] = []
    ok: list[dict] = []
    review: list[dict] = []

    for m in MATCHES:
        key = f"{m.home} - {m.away}"
        if key in played:
            continue
        rec = recommend_mpp_score(m.home, m.away, klement)
        rec["date"] = m.date
        by_date.setdefault(m.date, []).append(rec)

        if rec["confidence"] == "low":
            review.append(rec)
        elif rec["needs_action"]:
            if rec["user_score"] and rec["changed"]:
                to_change.append(rec)
            else:
                to_set.append(rec)
        else:
            ok.append(rec)

    def sort_key(r):
        return (r["date"].split("/")[1], r["date"].split("/")[0], r["key"])

    for bucket in (to_change, to_set, ok, review):
        bucket.sort(key=sort_key)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "V3",
        "played_skipped": len(played),
        "summary": {
            "to_change": len(to_change),
            "to_set": len(to_set),
            "ok": len(ok),
            "review": len(review),
        },
        "to_change": to_change,
        "to_set": to_set,
        "ok": ok,
        "review": review,
        "by_date": {d: sorted(rows, key=lambda r: r["key"]) for d, rows in sorted(by_date.items())},
    }


def format_text(guide: dict) -> str:
    lines = [
        "⚽ MPP — Guide grille V3 (fiable)",
        f"Généré : {guide['generated_at'][:19].replace('T', ' ')} UTC",
        "",
        "Logique : 1/N/2 = foule MPP → cotes → Klement | score exact = Poisson + différenciation (pas 1-0 par défaut).",
        "",
    ]

    s = guide["summary"]
    lines.append(f"📊 Résumé : {s['to_change']} à modifier | {s['to_set']} à saisir | {s['ok']} OK | {s['review']} à vérifier")
    lines.append("")

    if guide["to_change"]:
        lines.append("═══ 🔁 À MODIFIER sur mpp.football (confiance haute/moyenne) ═══")
        for r in guide["to_change"]:
            lines.append("")
            lines.append(f"📅 {r['date']} — {r['home']} vs {r['away']}")
            lines.append(f"   Actuel : {r['user_score']}  →  METS : {r['recommended_score'].replace('-', ' - ')}")
            lines.append(f"   1/N/2 : {r['reason']} | foule {r['crowd']}%")
            if r.get("exact_note"):
                lines.append(f"   Score exact : {r['exact_note']}")

    if guide["to_set"]:
        lines.append("")
        lines.append("═══ ➕ À SAISIR (pas encore dans ta grille) ═══")
        for r in guide["to_set"]:
            lines.append(f"📅 {r['date']} — {r['home']} vs {r['away']} → {r['recommended_score'].replace('-', ' - ')} ({r['reason']})")

    if guide["review"]:
        lines.append("")
        lines.append("═══ ⚠️  À VÉRIFIER (match serré, confiance basse) ═══")
        for r in guide["review"]:
            cur = r["user_score"] or "—"
            lines.append(
                f"📅 {r['date']} — {r['home']} vs {r['away']} | suggéré {r['recommended_score']} "
                f"(actuel {cur}) | foule {r['crowd']}% | {r['reason']}"
            )

    lines.append("")
    lines.append("═══ ✅ DÉJÀ BON (ne touche pas) ═══")
    for r in guide["ok"]:
        lines.append(f"   {r['date']} {r['home']} vs {r['away']} → {r['recommended_score']}")

    lines.append("")
    lines.append("→ https://mpp.football")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    guide = build_guide()
    OUT_JSON.write_text(json.dumps(guide, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json_only:
        print(OUT_JSON)
        return

    text = format_text(guide)
    print(text)
    print(f"\n→ JSON : {OUT_JSON}")


if __name__ == "__main__":
    main()
