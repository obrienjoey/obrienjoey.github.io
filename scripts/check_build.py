#!/usr/bin/env python3
"""Fail the build when a published page looks unfinished or leaks local paths.

Run straight after `hugo`:

    python3 scripts/check_build.py public

Every check here exists because the site shipped that mistake once. Add a new
check when a new class of "this should not go live" shows up.
"""

import re
import sys
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024  # skip anything implausibly large for a page

# (name, pattern, why)
CHECKS = [
    (
        "empty page title",
        re.compile(r"<title>\s*\|"),
        "front matter is missing `title`, so the tab and search results read '| Joey O'Brien'",
    ),
    (
        "empty h1",
        re.compile(r"<h1\b[^>]*>\s*</h1>"),
        "the page renders a blank heading where its title should be",
    ),
    (
        "zero date",
        re.compile(r"January 1, 0001"),
        "no `date` in front matter, so the page is dated year 1",
    ),
    (
        # Only file:/// URLs — a `C:\Dev\...` path inside a code block is a
        # legitimate thing for a tutorial post to contain.
        "local file path",
        re.compile(r"file:///"),
        "a working note with links to your machine's filesystem has been published",
    ),
]


def check(path: Path) -> list:
    if path.stat().st_size > MAX_BYTES:
        return []
    html = path.read_text(encoding="utf-8", errors="ignore")
    found = []
    for name, pattern, why in CHECKS:
        match = pattern.search(html)
        if match:
            line = html.count("\n", 0, match.start()) + 1
            snippet = html[max(0, match.start() - 30) : match.start() + 90]
            snippet = " ".join(snippet.split())
            found.append((name, why, line, snippet))
    return found


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_build.py <build-output-dir>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"check_build: {root} is not a directory — did the build run?", file=sys.stderr)
        return 2

    pages = sorted(root.rglob("*.html"))
    failures = 0
    for page in pages:
        for name, why, line, snippet in check(page):
            failures += 1
            rel = page.relative_to(root).as_posix()
            print(f"\nFAIL  {name}")
            print(f"      {rel}:{line}")
            print(f"      {why}")
            print(f"      ...{snippet}...")

    print()
    if failures:
        print(f"{failures} problem(s) across {len(pages)} pages — nothing deployed.")
        return 1
    print(f"OK — {len(pages)} pages, no problems found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
