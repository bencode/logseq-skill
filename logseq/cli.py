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
    p_find.add_argument("--non-empty", action="store_true",
                        help="Filter out files with no blocks (Logseq placeholder pages)")

    p_index = sub.add_parser("index", help="(Re)build SQLite index for a vault")
    p_index.add_argument("vault", help="Logseq vault directory (with logseq/config.edn)")
    p_index.add_argument("--full", action="store_true", help="Force full rebuild")

    p_stats = sub.add_parser("stats", help="Show index statistics for a vault")
    p_stats.add_argument("vault")

    p_search = sub.add_parser("search", help="FTS5 full-text search across vault blocks")
    p_search.add_argument("query", help="FTS5 query (phrases, AND/OR/NOT, prefix*)")
    p_search.add_argument("vault")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.add_argument("--snippet", action="store_true",
                          help="Include FTS5 snippet with «...» around matched terms")
    p_search.add_argument("--min-len", type=int, default=0,
                          help="Minimum block content length in chars (filter tag-spam)")

    p_back = sub.add_parser("backlinks", help="Find blocks linking to a given page")
    p_back.add_argument("name", help="Page name (case-insensitive by default)")
    p_back.add_argument("vault")
    p_back.add_argument("--limit", type=int, default=50)
    p_back.add_argument("--case-sensitive", action="store_true")
    p_back.add_argument("--include-bare", action="store_true",
                        help="Include blocks whose only content is [[name]] "
                             "(filtered out by default as noise)")

    p_todos = sub.add_parser("todos", help="List blocks with a task marker")
    p_todos.add_argument("vault")
    p_todos.add_argument("--marker", default="TODO",
                         help="Marker to filter (TODO/DOING/DONE/NOW/LATER/...)")
    p_todos.add_argument("--page", default=None, help="Limit to one page name")
    p_todos.add_argument("--limit", type=int, default=50)

    p_view = sub.add_parser(
        "view", help="Pretty-render a page with Rich (colored refs, tags, markers)"
    )
    p_view.add_argument(
        "name",
        help="Page name, 'today', 'YYYY-MM-DD', or a file path",
    )
    p_view.add_argument("vault", help="Logseq vault (with logseq/config.edn)")

    p_tui = sub.add_parser("tui", help="Launch the Textual TUI browser")
    p_tui.add_argument("vault", help="Logseq vault (with logseq/config.edn)")
    p_tui.add_argument(
        "--theme", default="catppuccin-mocha",
        help="Textual theme name (catppuccin-mocha, monokai, nord, "
             "gruvbox, dracula, tokyo-night, textual-dark, ...)",
    )

    args = p.parse_args(argv)

    if args.cmd == "parse":
        return _cmd_parse(args.file)
    if args.cmd == "page":
        return _cmd_page(args.file)
    if args.cmd == "journal":
        return _cmd_journal(args.date, args.in_dir)
    if args.cmd == "find-page":
        return _cmd_find_page(args.name, args.dirs, args.non_empty)
    if args.cmd == "index":
        return _cmd_index(args.vault, args.full)
    if args.cmd == "stats":
        return _cmd_stats(args.vault)
    if args.cmd == "search":
        return _cmd_search(
            args.query, args.vault, args.limit, args.snippet, args.min_len
        )
    if args.cmd == "backlinks":
        return _cmd_backlinks(
            args.name, args.vault, args.limit,
            args.case_sensitive, args.include_bare,
        )
    if args.cmd == "todos":
        return _cmd_todos(args.vault, args.marker, args.page, args.limit)
    if args.cmd == "view":
        return _cmd_view(args.name, args.vault)
    if args.cmd == "tui":
        return _cmd_tui(args.vault, args.theme)
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


def _cmd_find_page(name: str, dirs: list[str], non_empty: bool) -> int:
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
    from .parser import parse
    try:
        return len(parse(p.read_text(encoding="utf-8"), str(p)).blocks) > 0
    except (UnicodeDecodeError, OSError):
        return True  # err on the side of including; let caller decide


def _cmd_index(vault: str, full: bool) -> int:
    from .index import reindex
    try:
        result = reindex(Path(vault), full=full)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    _emit_json({
        "scanned": result.scanned,
        "skipped": result.skipped,
        "reindexed": result.reindexed,
        "deleted": result.deleted,
        "errors": result.errors,
        "auto_rebuilt": result.auto_rebuilt,
        "elapsed_ms": result.elapsed_ms,
    })
    return 0


def _cmd_stats(vault: str) -> int:
    from .stats import stats
    try:
        _emit_json(stats(Path(vault)))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


def _cmd_search(
    query: str, vault: str, limit: int, snippet: bool, min_len: int
) -> int:
    from .queries import search
    return _run_query(
        lambda: search(
            Path(vault), query, limit=limit, snippet=snippet, min_len=min_len
        )
    )


def _cmd_backlinks(
    name: str, vault: str, limit: int, case_sensitive: bool, include_bare: bool
) -> int:
    from .queries import backlinks
    return _run_query(
        lambda: backlinks(
            Path(vault), name, limit=limit,
            case_sensitive=case_sensitive, include_bare=include_bare,
        )
    )


def _cmd_todos(vault: str, marker: str, page: str | None, limit: int) -> int:
    from .queries import todos
    return _run_query(
        lambda: todos(Path(vault), marker=marker, page=page, limit=limit)
    )


def _cmd_tui(vault: str, theme: str) -> int:
    try:
        from .tui.app import run
    except ImportError as e:
        print(
            f"error: TUI requires `pip install -e \".[tui]\"` "
            f"(missing: {e.name})",
            file=sys.stderr,
        )
        return 2
    return run(Path(vault), theme=theme)


def _cmd_view(name: str, vault: str) -> int:
    try:
        path = _resolve_view_target(name, Path(vault))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 5
    from rich.console import Console
    from .parser import parse
    from .render import render_page
    text = path.read_text(encoding="utf-8")
    page = parse(text, str(path))
    Console().print(render_page(page))
    return 0


def _resolve_view_target(name: str, vault: Path) -> Path:
    from .index import validate_vault
    validate_vault(vault)
    if name == "today":
        from datetime import date
        return _journal_path_or_error(vault, date.today().isoformat())
    if _looks_like_date(name):
        return _journal_path_or_error(vault, name)
    if "/" in name or name.endswith(".md"):
        p = Path(name)
        if not p.is_absolute():
            p = (vault / p).resolve()
        if not p.exists():
            raise FileNotFoundError(f"file not found: {p}")
        return p
    needle = name.lower()
    candidates: list[Path] = []
    for sub in ("pages", "journals"):
        d = vault / sub
        if not d.exists():
            continue
        for md in d.glob("*.md"):
            if md.stem.lower() == needle:
                return md
            if needle in md.stem.lower():
                candidates.append(md)
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"no page matching {name!r} in {vault}")


def _looks_like_date(s: str) -> bool:
    parts = s.split("-")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def _journal_path_or_error(vault: Path, date_iso: str) -> Path:
    fname = "_".join(date_iso.split("-")) + ".md"
    p = vault / "journals" / fname
    if not p.exists():
        raise FileNotFoundError(f"journal not found: {p}")
    return p


def _run_query(fn):
    from .queries import IndexMissing, IndexStale
    try:
        _emit_json(fn())
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except IndexMissing as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except IndexStale as e:
        print(f"warn: {e}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
