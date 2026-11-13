#!/usr/bin/env python3
"""Import Simplified Chinese card names from 大学院废墟 (mtgch.com).

The site publishes community Simplified Chinese names (and text) per printing.
This tool only takes the *name* and only when the English name matches exactly;
anything else is skipped and reported. Output is a 17Lands-shaped overlay that
`build_dataset.py --lands` can consume.

  --registry  MTGA maintainer registry.sqlite (private, read-only)
  --run       run_id inside that registry (default: newest)
  --out       overlay json path
  --cache     response cache (re-runs do not re-request known printings)
  --sets      limit to these expansion codes (default: every row missing CJK)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://mtgch.com/api/v2/card"
CJK = re.compile(r"[\u3400-\u9fff]")
USER_AGENT = "mtga-card-names-import/1.0 (+https://github.com/1996Neil/mtga-card-names)"


def _same_name(found: str | None, expected: str) -> bool:
    """Exact match, tolerating only spacing/ellipsis rendering differences."""
    def norm(text):
        text = re.sub(r"\s+", " ", str(text or ""))
        text = re.sub(r"\s*\.\s*\.\s*\.", "...", text)
        return text.strip()
    return norm(found) == norm(expected)


def plain(value: str | None) -> str:
    text = re.sub(r"<[^>]*>", "", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def fetch(set_code: str, collector_number: str, cache: dict, cache_path: Path, delay: float) -> dict | None:
    key = f"{set_code}/{collector_number}"
    if key in cache:
        return cache[key]
    query = urllib.parse.urlencode({"set": set_code, "collector_number": collector_number})
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    try:
        payload = json.load(urllib.request.urlopen(request, timeout=25))
    except urllib.error.HTTPError as error:
        payload = {"_error": error.code} if error.code == 404 else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        payload = None
    if payload is None:
        return None
    cache[key] = payload
    cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    time.sleep(delay)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--run", default="")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path("/tmp/mtgch-name-cache.json"))
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--sets", nargs="*", default=None)
    args = parser.parse_args()

    connection = sqlite3.connect(f"file:{args.registry}?mode=ro", uri=True)
    run = args.run or connection.execute(
        "SELECT run_id FROM card_names ORDER BY run_id DESC LIMIT 1").fetchone()[0]
    rows = connection.execute(
        "SELECT arena_grp_id, identity_json, english_canonical, chinese_display "
        "FROM card_names WHERE run_id=? ORDER BY arena_grp_id", (run,)).fetchall()
    connection.close()

    cache = json.loads(args.cache.read_text()) if args.cache.is_file() else {}
    wanted = []
    for grp, identity_json, english, chinese in rows:
        if CJK.search(chinese or ""):
            continue
        identity = json.loads(identity_json or "{}")
        set_code = str(identity.get("ExpansionCode") or "")
        number = str(identity.get("CollectorNumber") or "")
        if not set_code or not number:
            continue
        if args.sets and set_code not in args.sets:
            continue
        wanted.append((grp, set_code, number, plain(english), identity))

    cards, skipped = [], []
    for grp, set_code, number, english, identity in wanted:
        # Tokens carry their own set (ttrk/ttrc) and collide with main-set
        # collector numbers, so look them up there first.
        candidates = [("t" + set_code, number)] if int(identity.get("IsToken") or 0) else []
        candidates.append((set_code, number))
        payload = None
        for candidate_set, candidate_number in candidates:
            payload = fetch(candidate_set, candidate_number, cache, args.cache, args.delay)
            if payload and not payload.get("_error") and _same_name(payload.get("name"), english):
                break
            payload = payload or {}
        if payload is None:
            skipped.append((set_code, number, english, "network"))
            continue
        if payload.get("_error"):
            skipped.append((set_code, number, english, f"http {payload['_error']}"))
            continue
        found = payload.get("name") or ""
        chinese = plain((payload.get("zhs_oracle") or {}).get("name"))
        if not _same_name(found, english):
            skipped.append((set_code, number, english, "english-mismatch:" + found[:40]))
            continue
        if not CJK.search(chinese):
            skipped.append((set_code, number, english, "no-chinese-name"))
            continue
        cards.append({
            "arena_id": str(grp),
            "english": english,
            "chinese": chinese,
            "set_code": set_code,
            "primary": int(identity.get("IsPrimaryCard") or 0),
            "face_type": int(identity.get("LinkedFaceType") or 0),
            "source": "mtgch.com 大学院废墟",
            "status": "community-translated-client-pending",
        })

    overlay = {"schema": 1, "source_sha256": "", "source": API, "run_id": run, "cards": cards}
    body = json.dumps(overlay, ensure_ascii=False, indent=1)
    import hashlib
    overlay["source_sha256"] = hashlib.sha256(
        json.dumps(cards, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(overlay, ensure_ascii=False, indent=1) + "\n")

    print(f"run={run} 待取={len(wanted)} 采用={len(cards)} 跳过={len(skipped)}")
    for item in skipped[:10]:
        print("  跳过", item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
