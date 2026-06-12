#!/usr/bin/env python3
"""Fusionne daily_predictions.json dans web/matches.json avant déploiement Pages."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "data" / "daily_predictions.json"
MATCHES = ROOT / "web" / "matches.json"
META = ROOT / "web" / "meta.json"


def main() -> None:
    if not MATCHES.exists():
        raise SystemExit(f"Missing {MATCHES}")

    matches = json.loads(MATCHES.read_text())
    by_key = {f"{m['home']} - {m['away']}": m for m in matches}

    updated = None
    if DAILY.exists():
        daily = json.loads(DAILY.read_text())
        updated = daily.get("generated_at")
        for p in daily.get("predictions", []):
            k = p.get("match")
            if k in by_key and p.get("score"):
                by_key[k]["suggested"] = p["score"]
                by_key[k]["today"] = True

    out = sorted(
        by_key.values(),
        key=lambda x: (x["date"].split("/")[1], x["date"].split("/")[0]),
    )
    MATCHES.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    META.write_text(
        json.dumps({"updated": updated, "site": "mpp-prono-agent"}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"✅ {len(out)} matchs prêts pour GitHub Pages")


if __name__ == "__main__":
    main()
