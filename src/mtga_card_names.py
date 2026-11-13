"""Reference loader for the MTGA names-only artifact (Python 3.9+).

The artifact is JSONL + manifest. ``cards.jsonl.gz`` is also supported.

Lookup semantics:

* identity is the Arena ``grp_id`` (not the English name; basic lands and
  rebalanced cards share names);
* ``zh is None`` means "no verified Chinese name" -- callers must fall back
  explicitly, never machine-translate;
* all display text is already plain text (tags stripped by the builder).
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class CardName:
    grp_id: int
    en: str
    zh: Optional[str]
    set: str = ""
    collector_number: str = ""
    is_primary: int = 0
    is_token: int = 0
    is_rebalanced: int = 0
    face_type: int = 0
    status: str = ""
    source: str = ""
    name_source: str = ""


class CardNameIndex:
    def __init__(self, cards: Iterable[CardName], manifest: Optional[dict] = None):
        self._cards = {card.grp_id: card for card in cards}
        self.manifest = manifest or {}

    @property
    def data_version(self) -> str:
        return str(self.manifest.get("data_version", ""))

    def __len__(self) -> int:
        return len(self._cards)

    def get(self, grp_id: int) -> Optional[CardName]:
        return self._cards.get(int(grp_id))

    def zh(self, grp_id: int) -> Optional[str]:
        card = self.get(grp_id)
        return card.zh if card else None

    def bilingual(self, grp_id: int, separator: str = " / ") -> Optional[str]:
        card = self.get(grp_id)
        if not card:
            return None
        return f"{card.zh}{separator}{card.en}" if card.zh else card.en

    def by_english(self, name: str) -> list[CardName]:
        wanted = " ".join(str(name).split())
        return [card for card in self._cards.values() if card.en == wanted]

    def by_chinese(self, name: str) -> list[CardName]:
        wanted = " ".join(str(name).split())
        return [card for card in self._cards.values() if card.zh == wanted]


def _open_text(directory: Path):
    plain = directory / "cards.jsonl"
    if plain.is_file():
        return plain.open(encoding="utf-8")
    gz = directory / "cards.jsonl.gz"
    if gz.is_file():
        return gzip.open(gz, "rt", encoding="utf-8")
    raise FileNotFoundError(f"cards.jsonl or cards.jsonl.gz not found in {directory}")


def load_card_names(directory: str | Path) -> CardNameIndex:
    """Load ``cards.jsonl`` / ``cards.jsonl.gz`` + ``manifest.json``."""
    root = Path(directory)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    cards: list[CardName] = []
    with _open_text(root) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            cards.append(CardName(
                grp_id=int(row["grp_id"]),
                en=row.get("en") or "",
                zh=row.get("zh"),
                set=row.get("set") or "",
                collector_number=row.get("collector_number") or "",
                is_primary=int(row.get("is_primary") or 0),
                is_token=int(row.get("is_token") or 0),
                is_rebalanced=int(row.get("is_rebalanced") or 0),
                face_type=int(row.get("face_type") or 0),
                status=row.get("status") or "",
                source=row.get("source") or "",
                name_source=row.get("name_source") or "",
            ))
    return CardNameIndex(cards, manifest)
