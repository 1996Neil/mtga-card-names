"""Advance the lightweight channel after an immutable data release is published.

Downloads only names-only assets using the existing GitHub CLI. No registry,
game files, credentials or private accounts enter the published channel.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from update_channel import advance, version_key

REPOSITORY = "1996Neil/mtga-card-names"
ROOT = Path(__file__).resolve().parents[1]


def download(tag, directory):
    version_key(tag.removeprefix("data-"))
    if not tag.startswith("data-"):
        raise ValueError("Only data-version release tags are accepted")
    meta = json.loads(subprocess.check_output(
        ["gh", "api", f"repos/{REPOSITORY}/releases/tags/{tag}"],
        text=True, timeout=15,
    ))
    if meta.get("draft") is not False or meta.get("prerelease") is not False:
        raise ValueError("The stable names channel only accepts published stable releases")
    subprocess.run([
        "gh", "release", "download", tag, "--repo", REPOSITORY,
        "--pattern", "manifest.json", "--pattern", "cards.jsonl.gz",
        "--dir", str(directory),
    ], check=True, timeout=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    args = parser.parse_args()
    version_key(args.tag.removeprefix("data-"))
    old = json.loads((ROOT / "updates/latest.json").read_text())
    if old["version"] == args.tag.removeprefix("data-"):
        print("Channel already current; no changes")
        return
    if version_key(args.tag.removeprefix("data-")) < version_key(old["version"]):
        raise ValueError("Refusing to roll back the update channel")
    with tempfile.TemporaryDirectory(prefix="card-names-channel-") as temporary:
        new, previous = Path(temporary) / "new", Path(temporary) / "previous"
        new.mkdir()
        previous.mkdir()
        download(args.tag, new)
        download("data-" + old["version"], previous)
        manifest = json.loads((new / "manifest.json").read_text())
        if manifest["data_version"] != args.tag.removeprefix("data-"):
            raise ValueError("Release version differs from its tag")
        print(json.dumps(advance(new, ROOT / "updates", previous)))


if __name__ == "__main__":
    main()
