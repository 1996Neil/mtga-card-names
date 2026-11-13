#!/usr/bin/env python3
"""Export the legacy 17Lands-zh snapshot schema from cards.jsonl.

The 17Lands fork currently reads resources/localization/cards.json with:
  {schema, source_sha256, cards: [{arena_id, english, chinese, set_code,
   primary, face_type, source, status}]}

This adapter lets that consumer switch to a pinned release without changing
its read_source() code. Rows without a Chinese name are omitted, matching the
existing snapshot behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, required=True, help="cards.jsonl")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    digest = hashlib.sha256(args.cards.read_bytes()).hexdigest()
    cards = []
    with args.cards.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("zh"):
                continue
            cards.append({
                "arena_id": str(row["grp_id"]),
                "english": row["en"],
                "chinese": row["zh"],
                "set_code": row.get("set") or "",
                "primary": int(row.get("is_primary") or 0),
                "face_type": int(row.get("face_type") or 0),
                "source": row.get("source") or "",
                "status": row.get("status") or "",
            })
    payload = {"schema": 1, "source_sha256": digest, "cards": cards}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(cards), "out": str(args.out), "source_sha256": digest}))


if __name__ == "__main__":
    main()
