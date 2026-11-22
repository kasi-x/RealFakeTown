#!/usr/bin/env python3
"""Copy the project's tree into GIFT/project/ (self-contained hand-over).

Everything that would otherwise be transferred via GitHub — the Unity project
sources (including `Assets/`, which is not committed yet), docs, tools — is
copied here so a single GIFT bundle reproduces the project. Heavy data
(PLATEAU SDK tarballs, CityGML, Library/, artifacts/) is deliberately NOT
copied: `make setup` / `make graph` fetch or regenerate it.

    python GIFT/tools/make_source.py            # REPO=.. -> GIFT/project
    python GIFT/tools/make_source.py --repo /path/to/repo --out /path/to/project
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

GIFT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=str(GIFT.parent), help="project root (default: GIFT's parent)")
    ap.add_argument("--out", default=str(GIFT / "project"), help="destination (default: GIFT/project)")
    ap.add_argument("--clean", action="store_true", help="wipe the destination first")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    out = pathlib.Path(args.out).resolve()
    if not (repo / "ProjectSettings" / "ProjectVersion.txt").is_file():
        raise SystemExit(f"not a Unity project root: {repo}")
    if out == repo or repo in out.parents and out == repo:
        raise SystemExit("refusing to copy the project onto itself")

    if args.clean and out.exists():
        shutil.rmtree(out)

    def ls(*extra: str) -> list[bytes]:
        return subprocess.check_output(["git", "-C", str(repo), "ls-files", "-z", *extra]).split(b"\0")

    # tracked + untracked-but-not-ignored: the bundle must carry work that has not
    # been committed yet (new directories are exactly where new work lands)
    listed = sorted({f for f in ls() + ls("--others", "--exclude-standard") if f})
    if not listed:
        raise SystemExit(f"git ls-files returned nothing for {repo}")

    copied, skipped = 0, 0
    for raw in listed:
        if not raw:
            continue
        rel = raw.decode("utf-8")
        if rel == "GIFT" or rel.startswith("GIFT/"):
            skipped += 1
            continue
        src, dst = repo / rel, out / rel
        if not src.is_file():
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"copied {copied} tracked files ({total/1e6:.2f} MB) -> {out}"
          + (f"  [skipped {skipped}]" if skipped else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
