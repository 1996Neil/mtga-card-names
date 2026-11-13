# MTGA Card Names (names-only)

A small, versioned **English ↔ Simplified Chinese card-name index** for MTG Arena,
keyed by Arena `GrpId`. It exists so tools such as draft helpers, coaches and
replay viewers can share one mapping instead of vendoring their own copies.

This repository contains **names only**. It does not contain rules text, flavor
text, UI strings, source evidence, or game files.

> This is an unofficial fan project. Card names and localized text belong to
> their respective rights holders. See [DATA-NOTICE.md](DATA-NOTICE.md).

## Data release

Latest: **`data-2026.64.50-r5`**

| File | Size | Description |
|---|---:|---|
| `cards.jsonl.gz` | ~0.9 MB | one JSON object per Arena `GrpId`, gzipped |
| `cards.jsonl` | ~8.8 MB | same, uncompressed |
| `manifest.json` | ~2 KB | versions, counts, source hashes, file hashes |
| `SHA256SUMS` | <1 KB | checksums for the release assets |

Counts for this release:

- **27,244** rows (unique `grp_id`)
- **27,236** with a Chinese name
- **8** without (templates / faces that have no localized title)
- **1,314** tokens, **20,260** primary cards

Download the assets from the repository's **Releases** page, verify
`SHA256SUMS`, and pin both the release tag and the manifest hash.

## Row format

```json
{"grp_id":6873,"title_id":2929,"set":"MIR","collector_number":"210",
 "is_primary":1,"is_token":0,"is_rebalanced":0,"face_type":0,
 "en":"Crash of Rhinos","zh":"猛进犀群",
 "display_enabled":1,"deck_import_enabled":1,
 "source":"new-official-card-identities+registry",
 "status":"static-verified-client-pending","name_source":"registry"}
```

| Field | Meaning |
|---|---|
| `grp_id` | Arena `GrpId`; the primary key |
| `title_id` | Arena `TitleId` |
| `set` | expansion code |
| `collector_number` | collector number, when known |
| `is_primary` | 1 = primary printing |
| `is_token` | 1 = token |
| `is_rebalanced` | 1 = Alchemy rebalanced (`A-` prefix) |
| `face_type` | Arena `LinkedFaceType` (0 = single face) |
| `en` | English card name, plain text |
| `zh` | Simplified Chinese name, plain text, or `null` |
| `display_enabled` | upstream display flag |
| `deck_import_enabled` | upstream deck-import flag |
| `source` | where the row identity came from |
| `status` | upstream compatibility status |
| `name_source` | `registry`, `baseline-titles`, `17lands-snapshot`, or `none` |

`zh: null` means **no verified Chinese name**. Consumers must fall back
explicitly (show English or "not available"); do not machine-translate.

## Usage

Python (no dependencies):

```python
from src.mtga_card_names import load_card_names

index = load_card_names("data")          # directory with cards.jsonl + manifest.json
card = index.get(6873)
print(card.en, card.zh)                  # Crash of Rhinos 猛进犀群
print(index.zh(6873))                    # 猛进犀群
```

Node (18+):

```js
import { loadCardNames } from './src/mtga-card-names.mjs';

const index = await loadCardNames('data');
console.log(index.zh(6873));             // 猛进犀群
```

Both loaders are reference implementations; the artifact is plain JSONL so any
language can read it.

## Why names-only

Other tools only need "what is this card called in Chinese". Shipping the full
localization corpus would be larger, copyright-heavier, and unnecessary for that
job. The private maintainer project keeps the full text; this repository only
publishes the name projection.

## Versions and updates

- `schema_version` changes only on breaking format changes.
- `data_version` is a game-build-based revision, e.g. `2026.64.50-r5`.
- Releases are immutable; a new game update gets a new tag.
- This release is a **top-up**: 57 missing names and 64 newer rows come from the
  2026-11-07 17Lands snapshot. It is not a complete new-game-build baseline;
  the manifest records the exact sources.

## Sources

- MTGA maintainer registry (`2026.64.50`, run `2026.64.50_20261021T054034265920Z`).
- 17Lands-zh snapshot (2026-11-07) for the top-up rows/names.

Card names may originate from the Arena client localization or community
review; `status` describes compatibility, not translation accuracy.

## Contributing

- Missing/wrong name: open an issue with `grp_id`, English name, current Chinese
  name, and a source (in-game screenshot or official announcement).
- Do not paste rules text or full localization dumps into issues.
- Do not submit game files, account data, or third-party database dumps.

## License

- **Code** (`src/`, `tools/`, `schema/`, tests): MIT. See [LICENSE](LICENSE).
- **Data** (`cards.jsonl`, `manifest.json`, releases): third-party content; no
  license is granted. See [DATA-NOTICE.md](DATA-NOTICE.md).
