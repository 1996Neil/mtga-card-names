"""Contract tests that do not need the full release dataset."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mtga_card_names import load_card_names  # noqa: E402

SAMPLE = ROOT / "samples" / "cards.sample.jsonl"
FIELDS = {
    "grp_id", "title_id", "set", "collector_number", "is_primary", "is_token",
    "is_rebalanced", "face_type", "en", "zh", "display_enabled",
    "deck_import_enabled", "source", "status", "name_source",
}


class ContractTest(unittest.TestCase):
    def test_sample_rows_have_exact_fields(self):
        rows = [json.loads(line) for line in SAMPLE.read_text(encoding="utf-8").splitlines() if line]
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertEqual(set(row), FIELDS)
            self.assertIsInstance(row["grp_id"], int)
            self.assertIsInstance(row["en"], str)
            self.assertTrue(row["en"])
            if row["zh"] is not None:
                self.assertIsInstance(row["zh"], str)
                self.assertRegex(row["zh"], r"[\u3400-\u9fff]")

    def test_python_loader_with_and_without_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copyfile(SAMPLE, root / "cards.jsonl")
            index = load_card_names(root)
            self.assertEqual(index.zh(6873), "猛进犀群")
            self.assertEqual(index.zh(107793), None)
            self.assertEqual(index.bilingual(6873), "猛进犀群 / Crash of Rhinos")
            self.assertIsNone(index.get(1))
            self.assertEqual(index.data_version, "")

            (root / "manifest.json").write_text(
                json.dumps({"data_version": "test-1"}, ensure_ascii=False), encoding="utf-8"
            )
            index = load_card_names(root)
            self.assertEqual(index.data_version, "test-1")

    def test_gzip_loader(self):
        import gzip
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with gzip.open(root / "cards.jsonl.gz", "wt", encoding="utf-8") as handle:
                handle.write(SAMPLE.read_text(encoding="utf-8"))
            index = load_card_names(root)
            self.assertEqual(index.zh(21519), "穿越裂罅")


if __name__ == "__main__":
    unittest.main()
