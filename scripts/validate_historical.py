#!/usr/bin/env python3
"""
Valide les pronos MPP avec l'historique API-Football (2022-2024).

Plan Free : saisons 2022-2024, pas le paramètre `last`, pas CDM 2026.
Sources :
  - Fréquences scores CDM 2022 (cache local ou API)
  - Forme équipes (cache api_team_form.json + CSV)

Usage:
  python scripts/build_form_cache.py      # rafraîchir forme depuis CSV/API connu
  python scripts/validate_historical.py   # mode offline (défaut)
  python scripts/validate_historical.py --fetch  # requête API si quota dispo
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from export_web import OVERRIDES
from mpp_grille_cdm import MATCHES, analyze, _with_odds
from mpp.models.poisson import score_matrix, top_exact_scores, estimate_lambdas_from_stats

env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if line.startswith("API_FOOTBALL_KEY="):
            os.environ.setdefault("API_FOOTBALL_KEY", line.split("=", 1)[1].strip())

API = "https://v3.football.api-sports.io"
IDS_CACHE = ROOT / "data" / "api_team_ids.json"
FORM_CACHE = ROOT / "data" / "api_team_form.json"
WC_CACHE = ROOT / "data" / "wc2022_scores.json"
REPORT_PATH = ROOT / "data" / "validation_report.json"
SEARCH_MAP = json.loads((ROOT / "data" / "team_search_map.json").read_text())
KNOWN_IDS: dict[str, int] = json.loads(IDS_CACHE.read_text()) if IDS_CACHE.exists() else {}


def api_get(endpoint: str, params: dict) -> dict:
    time.sleep(0.7)
    key = os.environ.get("API_FOOTBALL_KEY", "")
    r = requests.get(
        f"{API}/{endpoint}",
        headers={"x-apisports-key": key},
        params=params,
        timeout=30,
    )
    return r.json()


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def pick_national_team(results: list, search: str) -> int | None:
    """Choisit l'équipe nationale parmi les résultats de recherche."""
    search_l = search.lower()
    for item in results:
        team = item["team"]
        name = team["name"].lower()
        country = (team.get("country") or "").lower()
        if name == search_l or country == search_l:
            return team["id"]
    if results:
        return results[0]["team"]["id"]
    return None


def resolve_team_id(fr_name: str, ids_cache: dict[str, int]) -> int | None:
    if fr_name in ids_cache:
        return ids_cache[fr_name]
    if fr_name in KNOWN_IDS:
        ids_cache[fr_name] = KNOWN_IDS[fr_name]
        return KNOWN_IDS[fr_name]

    search = SEARCH_MAP.get(fr_name, fr_name)
    data = api_get("teams", {"search": search})
    if data.get("errors"):
        return None
    tid = pick_national_team(data.get("response", []), search)
    if tid:
        ids_cache[fr_name] = tid
    return tid


def wc2022_score_freq(fetch: bool = False) -> tuple[dict[str, float], int]:
    if not fetch and WC_CACHE.exists():
        cached = json.loads(WC_CACHE.read_text())
        return cached["frequencies"], cached.get("n_matches", 59)

    data = api_get("fixtures", {"league": 1, "season": 2022})
    scores = []
    for f in data.get("response", []):
        if f["fixture"]["status"]["short"] == "FT":
            hg, ag = f["goals"]["home"], f["goals"]["away"]
            if hg is not None:
                scores.append(f"{hg}-{ag}")
    cnt = Counter(scores)
    total = len(scores) or 1
    freqs = {s: c / total for s, c in cnt.items()}
    return freqs, len(scores)


def fetch_team_form(tid: int) -> dict:
    scored, conceded, n = 0.0, 0.0, 0
    for season in (2023, 2024):
        data = api_get("fixtures", {"team": tid, "season": season})
        if data.get("errors"):
            continue
        for f in data.get("response", []):
            if f["fixture"]["status"]["short"] != "FT":
                continue
            hg, ag = f["goals"]["home"], f["goals"]["away"]
            if hg is None:
                continue
            is_home = f["teams"]["home"]["id"] == tid
            scored += hg if is_home else ag
            conceded += ag if is_home else hg
            n += 1
    if n == 0:
        return {"scored": 1.25, "conceded": 1.25, "n": 0}
    return {"scored": round(scored / n, 2), "conceded": round(conceded / n, 2), "n": n}


def score_historical_label(score: str, wc_freq: dict[str, float]) -> tuple[str, str]:
    p = wc_freq.get(score, 0)
    if p >= 0.08:
        return "fréquent", f"fréquent CDM 2022 ({p*100:.1f}%)"
    if p >= 0.03:
        return "possible", f"possible CDM 2022 ({p*100:.1f}%)"
    return "rare", f"rare CDM 2022 ({p*100:.1f}%)"


def build_caches(unique_teams: list[str], refresh: bool = False) -> dict[str, dict]:
    ids_cache = load_json(IDS_CACHE)
    form_cache = load_json(FORM_CACHE)

    for name in unique_teams:
        if name not in ids_cache or refresh:
            resolve_team_id(name, ids_cache)
    save_json(IDS_CACHE, ids_cache)

    for name in unique_teams:
        if name in form_cache and not refresh and form_cache[name].get("n", 0) > 0:
            continue
        tid = ids_cache.get(name)
        if not tid:
            form_cache[name] = {"scored": 1.25, "conceded": 1.25, "n": 0, "id": None}
            continue
        form_cache[name] = {**fetch_team_form(tid), "id": tid}

    save_json(FORM_CACHE, form_cache)
    return form_cache


def load_form_cache() -> dict[str, dict]:
    if FORM_CACHE.exists():
        return json.loads(FORM_CACHE.read_text())
    return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true", help="Interroger l'API (quota journalier)")
    args = parser.parse_args()

    if args.fetch and not os.environ.get("API_FOOTBALL_KEY"):
        raise SystemExit("❌ API_FOOTBALL_KEY manquante dans .env")

    unique_teams = sorted({t for m in MATCHES for t in (m.home, m.away)})

    print("=" * 70)
    print("VALIDATION HISTORIQUE — GRILLE COMPLÈTE MPP CDM 2026")
    mode = "API live" if args.fetch else "cache local (CSV + API connu)"
    print(f"⚠️  Calibrage CDM 2022 + forme 2023-2024 — mode: {mode}")
    print("=" * 70)

    wc_freq, n_wc = wc2022_score_freq(fetch=args.fetch)
    top_wc = sorted(wc_freq.items(), key=lambda x: -x[1])[:8]
    print(f"\n📊 CDM 2022 — {n_wc} matchs analysés")
    for s, p in top_wc:
        print(f"   {s}: {p*100:.1f}%")

    if args.fetch:
        print(f"\n🔍 Résolution forme via API pour {len(unique_teams)} sélections...")
        form_cache = build_caches(unique_teams)
    else:
        form_cache = load_form_cache()
        if not form_cache:
            raise SystemExit("❌ Cache forme vide — lancer: python scripts/build_form_cache.py")
    with_data = sum(1 for v in form_cache.values() if v.get("n", 0) > 0)
    print(f"\n📋 Forme disponible : {with_data}/{len(unique_teams)} équipes")

    print("\n" + "=" * 70)
    print("ANALYSE MATCH PAR MATCH")
    print("=" * 70)

    results = []
    ok_model = 0
    ok_hist = 0
    partial = 0
    issues = []
    rare_scores = []

    for m in MATCHES:
        m = _with_odds(m)
        key = f"{m.home} - {m.away}"
        user_score = OVERRIDES.get(key, analyze(m)["score"])
        hs = form_cache.get(m.home, {"scored": 1.25, "conceded": 1.25, "n": 0})
        as_ = form_cache.get(m.away, {"scored": 1.25, "conceded": 1.25, "n": 0})

        api_top = "?"
        top3: list[str] = []
        if hs.get("n", 0) > 0 and as_.get("n", 0) > 0:
            lh, la = estimate_lambdas_from_stats(
                hs["scored"], hs["conceded"], as_["scored"], as_["conceded"]
            )
            top = top_exact_scores(score_matrix(lh, la), 5)
            api_top = top[0][0]
            top3 = [t[0] for t in top[:3]]
            if user_score == api_top or user_score in top3:
                ok_model += 1
                align = "✅"
            else:
                align = "⚠️"
                issues.append((key, user_score, api_top, top3))
        else:
            align = "○"
            partial += 1

        hist_cat, hist_note = score_historical_label(user_score, wc_freq)
        if hist_cat in ("fréquent", "possible"):
            ok_hist += 1
        else:
            rare_scores.append((key, user_score, hist_note))

        row = {
            "date": m.date,
            "match": key,
            "user_score": user_score,
            "api_top": api_top,
            "api_top3": top3,
            "align": align,
            "hist": hist_cat,
            "hist_note": hist_note,
            "home_form": hs,
            "away_form": as_,
        }
        results.append(row)

    # Affichage condensé par date
    by_date: dict[str, list] = {}
    for r in results:
        by_date.setdefault(r["date"], []).append(r)

    for date in sorted(by_date.keys(), key=lambda d: tuple(map(int, d.split("/")[::-1]))):
        print(f"\n### {date}")
        for r in by_date[date]:
            h, a = r["home_form"], r["away_form"]
            print(
                f"{r['align']} {r['match']:<38} toi:{r['user_score']:>4}  "
                f"modèle:{r['api_top']:>4}  [{r['hist']}]"
            )
            if h.get("n", 0) or a.get("n", 0):
                home = r["match"].split(" - ")[0]
                away = r["match"].split(" - ")[1]
                print(
                    f"     forme: {home} {h['scored']}M/{h['conceded']}B ({h.get('n',0)}m) — "
                    f"{away} {a['scored']}M/{a['conceded']}B ({a.get('n',0)}m)"
                )

    api_used = "cache (0 requête)"
    if args.fetch:
        st = api_get("status", {})
        reqs = st.get("response", {})
        if isinstance(reqs, dict):
            r = reqs.get("requests", {})
            api_used = f"{r.get('current')}/{r.get('limit_day')}"

    summary = {
        "total_matches": len(MATCHES),
        "aligned_model": ok_model,
        "aligned_historical": ok_hist,
        "partial_data": partial,
        "api_requests": api_used,
        "wc2022_top_scores": top_wc,
        "issues_model": [
            {"match": k, "user": u, "model": m, "top3": t3}
            for k, u, m, t3 in issues
        ],
        "rare_scores": [{"match": k, "score": s, "note": n} for k, s, n in rare_scores],
        "matches": results,
    }
    save_json(REPORT_PATH, summary)

    print("\n" + "=" * 70)
    print("RÉSUMÉ GLOBAL")
    print("=" * 70)
    print(f"Matchs analysés        : {len(MATCHES)}")
    print(f"Alignés modèle API     : {ok_model} (score dans top 3 forme 2023-24)")
    print(f"Scores réalistes CDM22 : {ok_hist}/{len(MATCHES)} (fréquent ou possible)")
    print(f"Données partielles     : {partial} matchs (équipe sans forme API)")
    print(f"Requêtes API aujourd'hui : {api_used}")
    print(f"Rapport JSON           : {REPORT_PATH}")

    if issues:
        print(f"\n⚠️  Écarts modèle ({len(issues)} matchs) — ton score hors top 3 forme API :")
        for k, u, m, t3 in issues[:12]:
            print(f"   {k}: toi {u} vs modèle {m} (top3: {', '.join(t3)})")
        if len(issues) > 12:
            print(f"   ... +{len(issues)-12} autres (voir JSON)")

    if rare_scores:
        print(f"\n🔴 Scores rares en CDM 2022 ({len(rare_scores)}) :")
        for k, s, n in rare_scores:
            print(f"   {k}: {s} ({n})")
    else:
        print("\n✅ Aucun score rare — toute la grille est dans le spectre CDM 2022")

    # Match ce soir
    tonight = [r for r in results if r["match"] == "Mexique - Afrique du Sud"]
    if tonight:
        t = tonight[0]
        print("\n🎯 CE SOIR — Mexique - Afrique du Sud")
        print(f"   Ton prono : {t['user_score']} | Modèle forme API : {t['api_top']}")
        print(f"   {t['hist_note']}")
        h, a = t["home_form"], t["away_form"]
        print(f"   Mexique {h['scored']} buts/m, {h['conceded']} encaissés ({h.get('n',0)} matchs)")
        print(f"   Afrique du Sud {a['scored']} buts/m, {a['conceded']} encaissés ({a.get('n',0)} matchs)")

    print("=" * 70)


if __name__ == "__main__":
    main()
