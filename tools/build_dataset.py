#!/usr/bin/env python3
"""Build the public names-only MTGA card-name dataset.

This tool is run by a maintainer who has the private inputs. It is intentionally
dependency-free and read-only.

Inputs:
  --registry  MTGA maintainer registry.sqlite (private)
  --lands     17Lands-zh resources/localization/cards.json (optional overlay)
  --titles    baseline portable/.../card-titles.jsonl (optional overlay)
  --base-version 2026.64.50
  --revision 5
  --out dist

Outputs:
  dist/cards.jsonl       one row per Arena GrpId, plain text only
  dist/cards.jsonl.gz    same, gzipped release asset
  dist/manifest.json     versions, counts, source hashes, file hashes
  dist/SHA256SUMS        sha256 of release assets
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "MTGA_CARD_NAMES_V1"
SCHEMA_VERSION = 1
CJK = re.compile(r"[\u3400-\u9fff]")
TAG = re.compile(r"<[^>]*>")
WHITESPACE = re.compile(r"\s+")

ROW_FIELDS = (
    "grp_id",
    "title_id",
    "set",
    "collector_number",
    "is_primary",
    "is_token",
    "is_rebalanced",
    "face_type",
    "en",
    "zh",
    "display_enabled",
    "deck_import_enabled",
    "source",
    "status",
    "name_source",
)


def plain_text(value: Any) -> str:
    """Strip Arena rich-text tags (``<nobr>``, ``<sprite ...>``) and entities."""
    if not isinstance(value, str):
        return ""
    value = TAG.sub("", value)
    value = html.unescape(value)
    return WHITESPACE.sub(" ", value).strip()


def clean_zh(value: Any, english: str) -> str | None:
    text = plain_text(value)
    if not CJK.search(text) or text == english:
        return None
    return text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def readonly_sqlite(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        sys.exit(f"[error] registry not found: {path}")
    base = path.resolve().as_uri()
    last: Exception | None = None
    for params in ("?mode=ro", "?mode=ro&immutable=1"):
        try:
            conn = sqlite3.connect(base + params, uri=True, timeout=5)
            conn.execute("select count(*) from card_names").fetchone()
            return conn
        except sqlite3.OperationalError as exc:
            last = exc
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                raise
    sys.exit(f"[error] cannot open registry read-only: {last}")


def latest_run(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "select run_id, count(*) c from card_names group by run_id order by run_id desc"
    ).fetchall()
    if not rows:
        sys.exit("[error] card_names is empty")
    for run_id, count in rows:
        if count > 1000:
            return run_id
    return rows[0][0]


def load_registry(conn: sqlite3.Connection, run_id: str) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    cursor = conn.execute(
        """
        select arena_grp_id, identity_json, english_canonical, chinese_display,
               display_enabled, deck_import_enabled, source, compatibility_status
        from card_names
        where run_id = ?
        order by arena_grp_id
        """,
        (run_id,),
    )
    for (grp_id, identity_json, english, chinese, display_enabled,
         deck_import_enabled, source, status) in cursor:
        grp_id = int(grp_id)
        if grp_id in out:
            raise SystemExit(f"[error] duplicate GrpId in {run_id}: {grp_id}")
        try:
            identity = json.loads(identity_json or "{}")
        except json.JSONDecodeError:
            identity = {}
        en = plain_text(english)
        if not en and not plain_text(chinese):
            # Placeholder identities (empty title in WC) are not card names.
            continue
        out[grp_id] = {
            "grp_id": grp_id,
            "title_id": int(identity.get("TitleId") or 0),
            "set": str(identity.get("ExpansionCode") or ""),
            "collector_number": str(identity.get("CollectorNumber") or ""),
            "is_primary": int(identity.get("IsPrimaryCard") or 0),
            "is_token": int(identity.get("IsToken") or 0),
            "is_rebalanced": int(en.startswith("A-")),
            "face_type": int(identity.get("LinkedFaceType") or 0),
            "en": en,
            "zh": clean_zh(chinese, en),
            "display_enabled": int(display_enabled or 0),
            "deck_import_enabled": int(deck_import_enabled or 0),
            "source": str(source or ""),
            "status": str(status or ""),
            "name_source": "registry" if clean_zh(chinese, en) else "none",
        }
    return out


def load_titles(path: Path) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            identity = row.get("identity") or {}
            out[int(row["grp_id"])] = {
                "en": plain_text(row.get("english")),
                "zh": plain_text(row.get("chinese")),
                "set": str(identity.get("ExpansionCode") or ""),
                "collector_number": str(identity.get("CollectorNumber") or ""),
                "is_primary": int(identity.get("IsPrimaryCard") or 0),
                "is_token": int(identity.get("IsToken") or 0),
                "is_rebalanced": int(identity.get("IsRebalanced") or 0),
                "face_type": int(identity.get("LinkedFaceType") or 0),
            }
    return out


def load_lands(path: Path) -> dict[int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[int, dict[str, Any]] = {}
    for card in payload.get("cards", []):
        en = plain_text(card.get("english"))
        out[int(card["arena_id"])] = {
            "en": en,
            "zh": plain_text(card.get("chinese")),
            "set": str(card.get("set_code") or ""),
            "collector_number": "",
            "is_primary": int(card.get("primary") or 0),
            "is_token": 0,
            "is_rebalanced": int(en.startswith("A-")),
            "face_type": int(card.get("face_type") or 0),
            "source": str(card.get("source") or ""),
            "status": str(card.get("status") or ""),
        }
    return out


def overlay_names(rows: dict[int, dict[str, Any]], overlay: dict[int, dict[str, Any]],
                  source_name: str) -> int:
    """Fill missing Chinese names, requiring the English name to agree."""
    filled = 0
    for grp_id, row in rows.items():
        if row["zh"]:
            continue
        candidate = overlay.get(grp_id)
        if not candidate or plain_text(candidate.get("en")) != row["en"]:
            continue
        zh = clean_zh(candidate.get("zh"), row["en"])
        if zh:
            row["zh"] = zh
            row["name_source"] = source_name
            filled += 1
    return filled


def add_overlay_extras(rows: dict[int, dict[str, Any]], overlay: dict[int, dict[str, Any]],
                       source_name: str) -> int:
    """Append rows that are absent from the registry but exist in the overlay."""
    added = 0
    for grp_id, card in overlay.items():
        if grp_id in rows:
            continue
        en = plain_text(card.get("en"))
        if not en:
            continue
        zh = clean_zh(card.get("zh"), en)
        rows[grp_id] = {
            "grp_id": grp_id,
            "title_id": 0,
            "set": str(card.get("set") or ""),
            "collector_number": str(card.get("collector_number") or ""),
            "is_primary": int(card.get("is_primary") or 0),
            "is_token": int(card.get("is_token") or 0),
            "is_rebalanced": int(card.get("is_rebalanced") or 0),
            "face_type": int(card.get("face_type") or 0),
            "en": en,
            "zh": zh,
            "display_enabled": 1,
            "deck_import_enabled": 1,
            "source": str(card.get("source") or ""),
            "status": str(card.get("status") or ""),
            "name_source": source_name if zh else "none",
        }
        added += 1
    return added


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--lands", type=Path)
    parser.add_argument("--titles", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-version", default="2026.64.50")
    parser.add_argument("--revision", type=int, default=5)
    parser.add_argument("--run", default="")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    registry_sha = sha256_file(args.registry)
    conn = readonly_sqlite(args.registry)
    try:
        run_id = args.run or latest_run(conn)
        rows = load_registry(conn, run_id)
    finally:
        conn.close()

    sources = [{
        "name": "maintenance-registry",
        "run_id": run_id,
        "sha256": registry_sha,
        "rows": len(rows),
    }]
    filled_from_lands = filled_from_titles = extra_lands = extra_titles = 0

    if args.titles:
        titles = load_titles(args.titles)
        filled_from_titles = overlay_names(rows, titles, "baseline-titles")
        extra_titles = add_overlay_extras(rows, titles, "baseline-titles")
        sources.append({
            "name": "baseline-titles",
            "sha256": sha256_file(args.titles),
            "rows": len(titles),
            "names_filled": filled_from_titles,
            "rows_added": extra_titles,
        })

    if args.lands:
        lands = load_lands(args.lands)
        filled_from_lands = overlay_names(rows, lands, "17lands-snapshot")
        extra_lands = add_overlay_extras(rows, lands, "17lands-snapshot")
        sources.append({
            "name": "17lands-snapshot",
            "sha256": sha256_file(args.lands),
            "rows": len(lands),
            "names_filled": filled_from_lands,
            "rows_added": extra_lands,
            "note": "2026-11-07 top-up snapshot; not a complete game-build baseline",
        })

    ordered = [rows[grp_id] for grp_id in sorted(rows)]
    cards_path = args.out / "cards.jsonl"
    count = write_jsonl(cards_path, ordered)
    gz_path = args.out / "cards.jsonl.gz"
    with cards_path.open("rb") as src, gzip.open(gz_path, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)

    with_zh = sum(1 for row in ordered if row["zh"])
    by_name_source: dict[str, int] = {}
    for row in ordered:
        by_name_source[row["name_source"]] = by_name_source.get(row["name_source"], 0) + 1
    data_version = f"{args.base_version}-r{args.revision}"

    manifest = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "data_version": data_version,
        "base_version": args.base_version,
        "revision": args.revision,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "counts": {
            "rows": count,
            "with_zh": with_zh,
            "missing_zh": count - with_zh,
            "unique_grp_ids": len({row["grp_id"] for row in ordered}),
            "by_name_source": by_name_source,
            "tokens": sum(1 for row in ordered if row["is_token"]),
            "primary": sum(1 for row in ordered if row["is_primary"]),
        },
        "sources": sources,
        "fields": list(ROW_FIELDS),
        "files": {
            "cards.jsonl": {
                "bytes": cards_path.stat().st_size,
                "sha256": sha256_file(cards_path),
            },
            "cards.jsonl.gz": {
                "bytes": gz_path.stat().st_size,
                "sha256": sha256_file(gz_path),
            },
        },
        "notes": (
            "Names-only projection: card titles and identity keys only. "
            "No rules text, flavor text, UI strings, source evidence, or raw game files. "
            "Rows added from the 17Lands snapshot are a top-up, not a complete game-build baseline."
        ),
        "notice": (
            "Card names and localized text belong to their respective rights holders. "
            "This is a derived fan index, not an official Wizards of the Coast product, "
            "and it does not grant redistribution rights. See DATA-NOTICE.md."
        ),
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out / "SHA256SUMS").write_text(
        "".join(
            f"{manifest['files'][name]['sha256']}  {name}\n"
            for name in ("cards.jsonl", "cards.jsonl.gz")
        ) + f"{sha256_file(args.out / 'manifest.json')}  manifest.json\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "run_id": run_id,
        "data_version": data_version,
        "rows": count,
        "with_zh": with_zh,
        "missing_zh": count - with_zh,
        "by_name_source": by_name_source,
        "filled_from_titles": filled_from_titles,
        "filled_from_lands": filled_from_lands,
        "extra_titles": extra_titles,
        "extra_lands": extra_lands,
        "out": str(args.out),
        "cards_sha256": manifest["files"]["cards.jsonl"]["sha256"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
