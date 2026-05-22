from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date
from pathlib import Path

from .parser import parse
from .serializer import to_dict


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="logseq")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_parse = sub.add_parser("parse", help="Parse a single .md file to JSON")
    p_parse.add_argument("file")

    p_page = sub.add_parser("page", help="Print only the page metadata of a file")
    p_page.add_argument("file")

    p_journal = sub.add_parser("journal", help="Parse a journal by date")
    p_journal.add_argument("date", help="'today' or YYYY-MM-DD")
    p_journal.add_argument("--in", dest="in_dir", required=True,
                           help="Logseq directory (containing journals/)")

    p_find = sub.add_parser("find-page", help="Find page files by name")
    p_find.add_argument("name")
    p_find.add_argument("dirs", nargs="+", help="One or more directories to search")

    p_index = sub.add_parser("index", help="(Re)build SQLite index for a vault")
    p_index.add_argument("vault", help="Logseq vault directory (with logseq/config.edn)")
    p_index.add_argument("--full", action="store_true", help="Force full rebuild")

    p_stats = sub.add_parser("stats", help="Show index statistics for a vault")
    p_stats.add_argument("vault")

    args = p.parse_args(argv)

    if args.cmd == "parse":
        return _cmd_parse(args.file)
    if args.cmd == "page":
        return _cmd_page(args.file)
    if args.cmd == "journal":
        return _cmd_journal(args.date, args.in_dir)
    if args.cmd == "find-page":
        return _cmd_find_page(args.name, args.dirs)
    if args.cmd == "index":
        return _cmd_index(args.vault, args.full)
    if args.cmd == "stats":
        return _cmd_stats(args.vault)
    return 2


def _emit_json(obj: object) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _cmd_parse(file: str) -> int:
    path = Path(file)
    text = path.read_text(encoding="utf-8")
    page = parse(text, str(path))
    _emit_json(to_dict(page))
    return 0


def _cmd_page(file: str) -> int:
    path = Path(file)
    text = path.read_text(encoding="utf-8")
    page = parse(text, str(path))
    _emit_json(to_dict(page)["page"])
    return 0


def _cmd_journal(date_arg: str, in_dir: str) -> int:
    if date_arg == "today":
        date_arg = _date.today().isoformat()
    parts = date_arg.split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        print(f"invalid date (expected 'today' or YYYY-MM-DD): {date_arg}", file=sys.stderr)
        return 2
    fname = "_".join(parts) + ".md"
    path = Path(in_dir) / "journals" / fname
    if not path.exists():
        print(f"journal not found: {path}", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")
    page = parse(text, str(path))
    _emit_json(to_dict(page))
    return 0


def _cmd_find_page(name: str, dirs: list[str]) -> int:
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

    for p in exact:
        print(f"exact\t{p}")
    if not exact:
        for p in substring:
            print(f"substring\t{p}")

    return 0 if (exact or substring) else 1


def _cmd_index(vault: str, full: bool) -> int:
    from .index import reindex
    result = reindex(Path(vault), full=full)
    _emit_json({
        "scanned": result.scanned,
        "skipped": result.skipped,
        "reindexed": result.reindexed,
        "deleted": result.deleted,
        "elapsed_ms": result.elapsed_ms,
    })
    return 0


def _cmd_stats(vault: str) -> int:
    from .index import stats
    _emit_json(stats(Path(vault)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
