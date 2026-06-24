#!/usr/bin/env python3
"""Applique la stratégie V2 sur les matchs restants et met à jour export_web.OVERRIDES."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from export_web import OVERRIDES, match_key  # noqa: E402
from mpp_grille_cdm import MATCHES  # noqa: E402
from mpp_recommend import recommend_mpp_score, load_klement  # noqa: E402

EXPORT_WEB = ROOT / "scripts" / "export_web.py"
BACKUP_DIR = ROOT / "data"
CHANGES_PATH = BACKUP_DIR / "v2_grille_changes.json"


def played_keys() -> set[str]:
  if (BACKUP_DIR / "live_tracker.json").exists():
    data = json.loads((BACKUP_DIR / "live_tracker.json").read_text(encoding="utf-8"))
    return {m["key"] for m in data.get("matches", []) if m.get("actual_score")}
  return set()


def backup_overrides() -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    path = BACKUP_DIR / f"overrides_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(OVERRIDES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def format_overrides_block(overrides: dict[str, str]) -> str:
    lines = ["OVERRIDES: dict[str, str] = {"]
    for key in sorted(overrides.keys()):
        lines.append(f'    "{key}": "{overrides[key]}",')
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_export_web(overrides: dict[str, str]) -> None:
    text = EXPORT_WEB.read_text(encoding="utf-8")
    new_block = format_overrides_block(overrides)
    updated, n = re.subn(
        r"OVERRIDES: dict\[str, str\] = \{.*?\n\}",
        new_block.rstrip(),
        text,
        count=1,
        flags=re.DOTALL,
    )
    if n != 1:
        raise RuntimeError("Impossible de mettre à jour OVERRIDES dans export_web.py")
    EXPORT_WEB.write_text(updated, encoding="utf-8")


def apply() -> dict:
    played = played_keys()
    klement = load_klement()
    new_overrides = dict(OVERRIDES)
    changes: list[dict] = []
    unchanged: list[dict] = []

    for m in MATCHES:
        key = match_key(m.home, m.away)
        if key in played:
            continue
        old = new_overrides.get(key) or ""
        rec = recommend_mpp_score(m.home, m.away, klement)
        new = rec["recommended_score"]
        new_overrides[key] = new
        row = {
            "key": key,
            "date": m.date,
            "home": m.home,
            "away": m.away,
            "old_score": old or None,
            "new_score": new,
            "tier": rec.get("tier"),
            "target_outcome": rec.get("target_outcome"),
            "p_draw": rec.get("p_draw"),
            "mpp_instruction": rec["mpp_instruction"],
        }
        if old and old != new:
            changes.append(row)
        elif not old:
            changes.append({**row, "old_score": "(nouveau)"})
        else:
            unchanged.append(row)

    backup_path = backup_overrides()
    write_export_web(new_overrides)

    payload = {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "V2",
        "played_skipped": len(played),
        "backup": str(backup_path),
        "changes": changes,
        "unchanged_count": len(unchanged),
        "all_upcoming": changes + unchanged,
    }
    CHANGES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = apply()
    print(f"✅ Stratégie V2 appliquée — {len(payload['changes'])} modification(s)")
    print(f"   Backup : {payload['backup']}")
    print(f"   Détail : {CHANGES_PATH}")
    for c in payload["changes"]:
        old = c.get("old_score") or "—"
        print(f"   • {c['key']}: {old} → {c['new_score']} (tier {c.get('tier')})")


if __name__ == "__main__":
    main()
