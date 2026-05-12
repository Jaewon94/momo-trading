#!/usr/bin/env python3
"""Validate local Markdown links in this repository."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SKIP_DIRS = {".git", ".pytest_cache", ".venv", "venv", "node_modules", "dist", "build", "coverage", "htmlcov"}
ALLOW_HIDDEN_DIRS = {".agent"}


def should_skip(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    for part in rel_parts:
        if part in SKIP_DIRS:
            return True
        if part.startswith(".") and part not in ALLOW_HIDDEN_DIRS:
            return True
    return False


def markdown_files(root: Path, paths: list[Path]) -> list[Path]:
    if paths:
        candidates = [(path if path.is_absolute() else root / path) for path in paths]
        expanded: list[Path] = []
        for path in candidates:
            if path.is_dir():
                expanded.extend(path.rglob("*.md"))
            elif path.suffix == ".md":
                expanded.append(path)
        return sorted(path for path in expanded if path.exists() and not should_skip(path, root))
    return sorted(path for path in root.rglob("*.md") if path.is_file() and not should_skip(path, root))


def normalize_link(raw: str) -> str:
    link = raw.strip()
    if link.startswith("<") and link.endswith(">"):
        link = link[1:-1]
    return unquote(link.split("#", 1)[0])


def is_external_or_anchor(link: str) -> bool:
    return link.startswith(("http://", "https://", "mailto:", "#", "tel:"))


def check_links(root: Path, paths: list[Path]) -> list[str]:
    missing: list[str] = []
    for path in markdown_files(root, paths):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in LINK_RE.finditer(text):
            link = normalize_link(match.group(1))
            if not link or is_external_or_anchor(link):
                continue
            target = (path.parent / link).resolve()
            if not str(target).startswith(str(root.resolve())):
                continue
            if not target.exists():
                missing.append(f"{path.relative_to(root)}: missing local link target: {link}")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    missing = check_links(root, args.paths)
    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1
    print("markdown link check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
