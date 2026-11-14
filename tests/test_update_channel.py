import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from update_channel import advance, load_release, version_key
from unittest.mock import patch

STATUS = "static-verified-client-pending"


def release(folder, version, rows):
    folder.mkdir(parents=True)
    raw = ("\n".join(json.dumps({
        "grp_id": aid, "en": en, "zh": zh, "set": "TST", "is_primary": 1,
        "face_type": 0, "source": "fixture", "status": STATUS,
    }, ensure_ascii=False) for aid, en, zh in rows) + "\n").encode()
    compressed = gzip.compress(raw)
    (folder / "cards.jsonl.gz").write_bytes(compressed)
    manifest = {"data_version": version, "counts": {"with_zh": len(rows)}, "files": {
        "cards.jsonl": {"sha256": hashlib.sha256(raw).hexdigest()},
        "cards.jsonl.gz": {"sha256": hashlib.sha256(compressed).hexdigest()},
    }}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder


class UpdateChannelTests(unittest.TestCase):
    def test_version_order_is_numeric(self):
        self.assertGreater(version_key("2026.65.0-r10"), version_key("2026.65.0-r2"))
        for bad in ("latest", "../x", "2026.65.0-r0"):
            with self.assertRaises(ValueError):
                version_key(bad)

    def test_bootstrap_is_tiny_and_contains_no_full_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = release(root / "data", "2026.65.0-r1", [(1, "Card", "卡牌")])
            index = advance(data, root / "updates")
            self.assertEqual(index["patches"], [])
            self.assertLess((root / "updates/latest.json").stat().st_size, 128)

    def test_changes_only_and_immutable_forward_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = release(root / "old", "2026.65.0-r1", [(1, "Same", "相同"), (2, "Fix", "原名"), (3, "Removed", "删除")])
            new = release(root / "new", "2026.65.0-r2", [(1, "Same", "相同"), (2, "Fix", "新名"), (4, "New", "新增")])
            advance(old, root / "updates")
            index = advance(new, root / "updates", old)
            edge = index["patches"][0]
            raw = (root / "updates" / edge["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), edge["sha256"])
            patch = json.loads(gzip.decompress(raw))
            self.assertEqual([r["arena_id"] for r in patch["upserts"]], ["2", "4"])
            self.assertEqual(patch["removes"], ["3"])
            self.assertNotIn("Same", gzip.decompress(raw).decode())
            with self.assertRaises(ValueError):
                advance(new, root / "updates", old)

    def test_rejects_corrupt_release(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = release(Path(directory) / "data", "2026.65.0-r1", [(1, "Card", "卡牌")])
            (folder / "cards.jsonl.gz").write_bytes(b"not a release")
            with self.assertRaises(ValueError):
                load_release(folder)

    def test_rejects_duplicate_or_markup_names(self):
        for rows in ([(1, "Card", "卡"), (1, "Other", "其他")], [(1, "Card", "<b>卡</b>")]):
            with tempfile.TemporaryDirectory() as directory:
                folder = release(Path(directory) / "data", "2026.65.0-r1", rows)
                with self.assertRaises(ValueError):
                    load_release(folder)

    def test_publisher_rejects_client_incompatible_fields(self):
        for key, value in (("grp_id", -1), ("grp_id", 12345678901),
                           ("is_primary", 2), ("face_type", 101),
                           ("en", ""), ("source", "")):
            with self.subTest(field=key, value=value), tempfile.TemporaryDirectory() as directory:
                folder = release(Path(directory) / "data", "2026.65.0-r1", [(1, "Card", "卡牌")])
                content = json.loads(gzip.decompress((folder / "cards.jsonl.gz").read_bytes()))
                content[key] = value
                raw = (json.dumps(content) + "\n").encode()
                compressed = gzip.compress(raw)
                (folder / "cards.jsonl.gz").write_bytes(compressed)
                manifest = json.loads((folder / "manifest.json").read_text())
                manifest["files"]["cards.jsonl"]["sha256"] = hashlib.sha256(raw).hexdigest()
                manifest["files"]["cards.jsonl.gz"]["sha256"] = hashlib.sha256(compressed).hexdigest()
                (folder / "manifest.json").write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    load_release(folder)

    def test_rejects_patch_above_client_byte_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = release(root / "old", "2026.65.0-r1", [(1, "Card", "卡牌")])
            new = release(root / "new", "2026.65.0-r2", [(1, "Card", "新名")])
            advance(old, root / "updates")
            with patch("update_channel.gzip.compress", return_value=b"x" * (2 * 1024 * 1024 + 1)):
                with self.assertRaisesRegex(ValueError, "Compressed patch"):
                    advance(new, root / "updates", old)
            self.assertEqual(json.loads((root / "updates/latest.json").read_text())["version"], "2026.65.0-r1")

    def test_stable_channel_rejects_draft_and_prerelease(self):
        from publish_update_channel import download
        for flags in ({"draft": True, "prerelease": False}, {"draft": False, "prerelease": True}):
            with patch("publish_update_channel.subprocess.check_output", return_value=json.dumps(flags)):
                with self.assertRaisesRegex(ValueError, "stable releases"):
                    download("data-2026.65.0-r2", Path("/not-used"))

    def test_published_channel_files_match_their_hashes(self):
        root = Path(__file__).resolve().parents[1] / "updates"
        index = json.loads((root / "latest.json").read_text())
        version_key(index["version"])
        self.assertLessEqual((root / "latest.json").stat().st_size, 32768)
        previous = None
        for edge in index["patches"]:
            if previous is not None:
                self.assertEqual(edge["from"], previous)
            self.assertEqual(edge["file"], f"patches/{edge['sha256']}.json.gz")
            raw = (root / edge["file"]).read_bytes()
            self.assertEqual(len(raw), edge["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), edge["sha256"])
            patch = json.loads(gzip.decompress(raw))
            self.assertEqual((patch["from"], patch["to"]), (edge["from"], edge["to"]))
            previous = edge["to"]
        if previous:
            self.assertEqual(previous, index["version"])
