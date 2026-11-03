"""Check that every [[wiki link]] in knowledge/ points at an existing note.

    python scripts/check_links.py

Links are vault-relative paths ("Projects/AutoCAD-MCP/index") or bare note names
("wiki-protocol", "Change log"), optionally with "|alias" or "#heading".
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT = os.path.join(ROOT, "knowledge")
LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
CODE = re.compile(r"`[^`]*`")


def main() -> int:
    notes, names = set(), set()
    for folder, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            rel = os.path.relpath(os.path.join(folder, f), VAULT).replace(os.sep, "/")
            notes.add(rel)
            if rel.endswith(".md"):
                notes.add(rel[:-3])
                names.add(os.path.basename(rel[:-3]))
    broken = []
    for note in sorted(n for n in notes if n.endswith(".md")):
        with open(os.path.join(VAULT, note), encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                for target in LINK.findall(CODE.sub("", line)):
                    target = target.strip()
                    if target not in notes and target not in names:
                        broken.append(f"{note}:{lineno}: [[{target}]]")
    for b in broken:
        print("broken link:", b)
    print(f"{len(broken)} broken link(s) in {sum(n.endswith('.md') for n in notes)} notes.")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
