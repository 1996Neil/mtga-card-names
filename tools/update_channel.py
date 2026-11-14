"""Build immutable names-only row deltas for the lightweight desktop updater.

Initial channel: --data dist --out updates
Next release:   --data new-dist --previous old-dist --out updates
Only a publisher reads full releases. Clients fetch latest.json once at startup
and only download patches linking their installed version to the newest one.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re

VERSION = re.compile(r"([0-9]{4})\.([0-9]{1,3})\.([0-9]{1,3})-r([1-9][0-9]{0,4})")
FIELDS = ("arena_id", "english", "chinese", "set_code", "primary", "face_type", "source", "status")
TRUSTED = {"static-verified-client-pending", "native-regression-passed;unsampled-cards-static-only"}


def version_key(value):
    match = VERSION.fullmatch(value)
    if not match:
        raise ValueError("Invalid names version")
    return tuple(map(int, match.groups()))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def load_release(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    version_key(manifest["data_version"])
    compressed = (directory / "cards.jsonl.gz").read_bytes()
    if hashlib.sha256(compressed).hexdigest() != manifest["files"]["cards.jsonl.gz"]["sha256"]:
        raise ValueError("Gzip hash mismatch")
    raw = gzip.decompress(compressed)
    if hashlib.sha256(raw).hexdigest() != manifest["files"]["cards.jsonl"]["sha256"]:
        raise ValueError("JSONL hash mismatch")
    result = {}
    for line in raw.decode().splitlines():
        row = json.loads(line)
        if not row.get("zh"):
            continue
        card = dict(zip(FIELDS, (
            str(row["grp_id"]), row["en"], row["zh"], row["set"],
            int(row["is_primary"]), int(row["face_type"]), row["source"], row["status"],
        )))
        if (not re.fullmatch(r"[1-9][0-9]{0,9}", card["arena_id"]) or card["arena_id"] in result or
                card["status"] not in TRUSTED or not re.search(r"[\u3400-\u9fff]", card["chinese"]) or
                card["primary"] not in (0, 1) or not 0 <= card["face_type"] <= 100 or
                any(not isinstance(card[k], str) or not card[k] or len(card[k]) > 1024 or
                    re.search(r"[\x00-\x1f<>]", card[k])
                    for k in ("english", "chinese", "source", "set_code"))):
            raise ValueError("Invalid names-only row")
        result[card["arena_id"]] = card
    if not 0 < len(result) <= 100000 or len(result) != manifest["counts"]["with_zh"]:
        raise ValueError("Row count mismatch")
    return manifest["data_version"], result


def advance(data, out, previous=None):
    version, cards = load_release(data)
    index_path = out / "latest.json"
    if not index_path.exists():
        if previous is not None:
            raise ValueError("Bootstrap the channel before adding a patch")
        index = {"schema": 1, "version": version, "rows": len(cards), "patches": []}
    else:
        index = json.loads(index_path.read_text())
        if previous is None:
            raise ValueError("Existing channel requires the previous release")
        old_version, old_cards = load_release(previous)
        if index["version"] != old_version or index["rows"] != len(old_cards):
            raise ValueError("Previous release must match the published channel head")
        if version_key(version) <= version_key(old_version):
            raise ValueError("Versions must increase; never replace published versions")
        upserts = [cards[k] for k in sorted(cards, key=int) if old_cards.get(k) != cards[k]]
        removes = sorted(old_cards.keys() - cards.keys(), key=int)
        patch = {"schema": 1, "from": old_version, "to": version, "rows": len(cards),
                 "upserts": upserts, "removes": removes}
        patch_bytes = encoded(patch)
        if len(patch_bytes) > 16 * 1024 * 1024:
            raise ValueError("Expanded patch exceeds the client byte budget")
        compressed = gzip.compress(patch_bytes, mtime=0)
        if len(compressed) > 2 * 1024 * 1024:
            raise ValueError("Compressed patch exceeds the client byte budget")
        sha = hashlib.sha256(compressed).hexdigest()
        relative = f"patches/{sha}.json.gz"
        destination = out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != compressed:
            raise ValueError("Refusing to replace an immutable patch")
        destination.write_bytes(compressed)
        edge = {"from": old_version, "to": version, "file": relative,
                "sha256": sha, "bytes": len(compressed), "rows": len(cards),
                "upserts": len(upserts), "removes": len(removes)}
        chain = [*index["patches"], edge][-64:]
        while sum(item["bytes"] for item in chain) > 4 * 1024 * 1024:
            chain.pop(0)
        index = {"schema": 1, "version": version, "rows": len(cards), "patches": chain}
    payload = encoded(index)
    if len(payload) > 32768:
        raise ValueError("Version manifest exceeds the client size budget")
    out.mkdir(parents=True, exist_ok=True)
    index_path.write_bytes(payload)
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(advance(args.data, args.out, args.previous), ensure_ascii=False))
