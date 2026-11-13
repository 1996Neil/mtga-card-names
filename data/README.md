# Data directory

The release artifacts are **not committed** to Git. Download them from the
repository's Releases page:

- `cards.jsonl.gz`
- `manifest.json`
- `SHA256SUMS`

Example:

```bash
mkdir -p data
gh release download data-2026.64.50-r5 --dir data \
  --pattern 'cards.jsonl.gz' --pattern 'manifest.json' --pattern 'SHA256SUMS'
cd data && shasum -a 256 -c SHA256SUMS
```

Or with curl:

```bash
base=https://github.com/1996Neil/mtga-card-names/releases/download/data-2026.64.50-r5
curl -L -O "$base/cards.jsonl.gz" -O "$base/manifest.json" -O "$base/SHA256SUMS"
```

Always pin the release tag and verify the checksums before use. Do not read
`main` or an unversioned artifact.
