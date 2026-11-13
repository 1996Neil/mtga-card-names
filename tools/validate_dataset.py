#!/usr/bin/env python3
"""Validate a names-only release directory against the v1 contract.

Usage:
    python3 tools/validate_dataset.py --data dist
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

CJK = re.compile(r"[\u3400-\u9fff]")
TAG = re.compile(r"<[^>]*>")
ENTITY = re.compile(r"&(#x[\da-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);", re.I)
PATH = re.compile(r"(/Users/|/home/|[A-Za-z]:\\\\|file://)")
FIELDS = {
    "grp_id", "title_id", "set", "collector_number", "is_primary", "is_token",
    "is_rebalanced", "face_type", "en", "zh", "display_enabled",
    "deck_import_enabled", "source", "status", "name_source",
}
NAME_SOURCES = {"registry", "baseline-titles", "17lands-snapshot", "mtgch-zhs", "none"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()

    errors: list[str] = []
    manifest_path = args.data / "manifest.json"
    if not manifest_path.is_file():
        sys.exit(f"[error] missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest.get("schema") != "MTGA_CARD_NAMES_V1":
        fail(errors, f"unexpected schema: {manifest.get('schema')!r}")
    if manifest.get("schema_version") != 1:
        fail(errors, f"unexpected schema_version: {manifest.get('schema_version')!r}")

    files = manifest.get("files") or {}
    plain_path = args.data / "cards.jsonl"
    gz_path = args.data / "cards.jsonl.gz"
    if not plain_path.is_file() and not gz_path.is_file():
        sys.exit(f"[error] missing cards.jsonl or cards.jsonl.gz in {args.data}")
    for name, path in (("cards.jsonl", plain_path), ("cards.jsonl.gz", gz_path)):
        if not path.is_file():
            # A release consumer may download only one representation.
            continue
        entry = files.get(name)
        if not entry:
            fail(errors, f"manifest missing file entry: {name}")
            continue
        if path.stat().st_size != entry.get("bytes"):
            fail(errors, f"{name}: size mismatch")
        if sha256_file(path) != entry.get("sha256"):
            fail(errors, f"{name}: sha256 mismatch")

    cards_path = plain_path
    open_cards = None
    if plain_path.is_file():
        open_cards = plain_path.open(encoding="utf-8")
    elif gz_path.is_file():
        open_cards = gzip.open(gz_path, "rt", encoding="utf-8")

    seen: set[int] = set()
    rows = 0
    with_zh = 0
    tokens = 0
    primary = 0
    by_source: dict[str, int] = {}
    with open_cards as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            rows += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                fail(errors, f"line {line_no}: invalid JSON: {exc}")
                continue
            if set(row) != FIELDS:
                fail(errors, f"line {line_no}: field set mismatch: {sorted(set(row) ^ FIELDS)}")
                continue
            grp_id = row["grp_id"]
            if not isinstance(grp_id, int) or grp_id <= 0:
                fail(errors, f"line {line_no}: invalid grp_id")
            elif grp_id in seen:
                fail(errors, f"line {line_no}: duplicate grp_id {grp_id}")
            seen.add(grp_id)

            if not isinstance(row["en"], str) or not row["en"].strip():
                fail(errors, f"line {line_no}: empty en")
            if len(row["en"]) > 128:
                fail(errors, f"line {line_no}: en too long")
            zh = row["zh"]
            if zh is not None:
                if not isinstance(zh, str) or not CJK.search(zh):
                    fail(errors, f"line {line_no}: zh has no Han characters")
                elif zh == row["en"]:
                    fail(errors, f"line {line_no}: zh equals en")
                elif len(zh) > 128:
                    fail(errors, f"line {line_no}: zh too long")
                else:
                    with_zh += 1
            for field in ("en", "zh", "set", "collector_number", "source", "status"):
                value = row[field]
                if isinstance(value, str) and (TAG.search(value) or ENTITY.search(value)):
                    fail(errors, f"line {line_no}: {field} contains markup/entities")
                if isinstance(value, str) and PATH.search(value):
                    fail(errors, f"line {line_no}: {field} contains a local path")
            for field in ("is_primary", "is_token", "is_rebalanced", "display_enabled",
                          "deck_import_enabled"):
                if row[field] not in (0, 1):
                    fail(errors, f"line {line_no}: {field} must be 0/1")
            if row["name_source"] not in NAME_SOURCES:
                fail(errors, f"line {line_no}: invalid name_source {row['name_source']!r}")
            by_source[row["name_source"]] = by_source.get(row["name_source"], 0) + 1
            tokens += int(row["is_token"] == 1)
            primary += int(row["is_primary"] == 1)

    counts = manifest.get("counts") or {}
    expected = {
        "rows": rows,
        "with_zh": with_zh,
        "missing_zh": rows - with_zh,
        "unique_grp_ids": len(seen),
        "tokens": tokens,
        "primary": primary,
        "by_name_source": by_source,
    }
    for key, value in expected.items():
        if counts.get(key) != value:
            fail(errors, f"manifest counts.{key}: {counts.get(key)!r} != {value!r}")

    # If both representations exist, they must decode to exactly the same bytes.
    if plain_path.is_file() and gz_path.is_file():
        with gzip.open(gz_path, "rb") as handle:
            if handle.read() != plain_path.read_bytes():
                fail(errors, "cards.jsonl.gz does not decode to cards.jsonl")

    if errors:
        print(f"INVALID: {len(errors)} error(s)", file=sys.stderr)
        for error in errors[:50]:
            print(f"  - {error}", file=sys.stderr)
        raise SystemExit(1)

    print(json.dumps({
        "valid": True,
        "data_version": manifest.get("data_version"),
        "rows": rows,
        "with_zh": with_zh,
        "missing_zh": rows - with_zh,
        "tokens": tokens,
        "primary": primary,
        "by_name_source": by_source,
        "cards_sha256": files["cards.jsonl"]["sha256"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
