from __future__ import annotations

import json
import sys
from datetime import date as _date
from pathlib import Path

from ..parser import parse
from ..serializer import to_dict


def emit_json(obj: object) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def cmd_parse(file: str) -> int:
    path = Path(file)
    text = path.read_text(encoding="utf-8")
    page = parse(text, str(path))
    emit_json(to_dict(page))
    return 0


def cmd_page(file: str) -> int:
    path = Path(file)
    text = path.read_text(encoding="utf-8")
    page = parse(text, str(path))
    emit_json(to_dict(page)["page"])
    return 0


def cmd_journal(date_arg: str, in_dir: str) -> int:
    if date_arg == "today":
        date_arg = _date.today().isoformat()
    parts = date_arg.split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        print(
            f"invalid date (expected 'today' or YYYY-MM-DD): {date_arg}",
            file=sys.stderr,
        )
        return 2
    fname = "_".join(parts) + ".md"
    path = Path(in_dir) / "journals" / fname
    if not path.exists():
        print(f"journal not found: {path}", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")
    page = parse(text, str(path))
    emit_json(to_dict(page))
    return 0


def cmd_find_page(name: str, dirs: list[str], non_empty: bool) -> int:
    needle = name.lower()
    exact: list[Path] = []
    substring: list[Path] = []
    for d in dirs:
        root = Path(d)
        if not root.exists():
            print(f"directory not found: {root}", file=sys.stderr)
            continue
        for md in root.rglob("*.md"):
            stem_lower = md.stem.lower()
            if stem_lower == needle:
                exact.append(md.resolve())
            elif needle in stem_lower:
                substring.append(md.resolve())

    if non_empty:
        exact = [p for p in exact if _file_has_blocks(p)]
        substring = [p for p in substring if _file_has_blocks(p)]

    for p in exact:
        print(f"exact\t{p}")
    if not exact:
        for p in substring:
            print(f"substring\t{p}")

    return 0 if (exact or substring) else 1


def _file_has_blocks(p: Path) -> bool:
    try:
        return len(parse(p.read_text(encoding="utf-8"), str(p)).blocks) > 0
    except (UnicodeDecodeError, OSError):
        return True  # err on the side of including; let caller decide
