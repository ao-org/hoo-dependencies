#!/usr/bin/env python3
"""Create deterministic archives from already-audited dependency checkouts.

This publishing helper performs no network access. Run it in the controlled
ao-org/hoo-dependencies publishing process, then publish its archives there.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent.parent

def run(command): return subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout
def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): result.update(block)
    return result.hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True, metavar="NAME=/ABSOLUTE/CHECKOUT")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); lock = {"applicationSources": json.loads((Path(__file__).parent / "application-sources.json").read_text())}
    expected = {item["name"]: item for item in lock["applicationSources"]}; supplied = {}
    for value in args.source:
        name, separator, path = value.partition("=")
        if not separator or name in supplied: raise SystemExit("Invalid/duplicate --source: " + value)
        supplied[name] = Path(path).resolve()
    if set(supplied) != set(expected): raise SystemExit("Supply exactly: " + ", ".join(sorted(expected)))
    args.output.mkdir(parents=True, exist_ok=False); manifest = []
    for name in sorted(supplied):
        source, item = supplied[name], expected[name]; revision = item["revision"]
        if run(["git", "-C", str(source), "rev-parse", "{}^{{commit}}".format(revision)]).decode().strip() != revision:
            raise SystemExit("Checkout lacks pinned commit: " + name)
        raw = run(["git", "-C", str(source), "archive", "--format=tar", "--prefix={}/".format(name), revision])
        archive = args.output / (name + "-" + revision + ".tar.gz")
        with archive.open("wb") as output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed: compressed.write(raw)
        manifest.append({"name": name, "revision": revision, "license": item["license"],
                         "file": archive.name, "size": archive.stat().st_size, "sha256": digest(archive), "archiveRoot": name})
    (args.output / "manifest.json").write_text(json.dumps({"schema": 1, "sources": manifest}, indent=2, sort_keys=True) + "\n")

if __name__ == "__main__": main()
