from __future__ import annotations

import argparse
import sys

from .commands import atomic, db, tui, view


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
        "--theme", default="textual-dark",
        help="Initial theme name. Press T inside the TUI to live-preview "
             "all available themes (12 built-in + logseq-black + logseq-white).",
    )

    args = p.parse_args(argv)
    return _dispatch(args)


def _dispatch(args: argparse.Namespace) -> int:
    if args.cmd == "parse":
        return atomic.cmd_parse(args.file)
    if args.cmd == "page":
        return atomic.cmd_page(args.file)
    if args.cmd == "journal":
        return atomic.cmd_journal(args.date, args.in_dir)
    if args.cmd == "find-page":
        return atomic.cmd_find_page(args.name, args.dirs, args.non_empty)
    if args.cmd == "index":
        return db.cmd_index(args.vault, args.full)
    if args.cmd == "stats":
        return db.cmd_stats(args.vault)
    if args.cmd == "search":
        return db.cmd_search(
            args.query, args.vault, args.limit, args.snippet, args.min_len
        )
    if args.cmd == "backlinks":
        return db.cmd_backlinks(
            args.name, args.vault, args.limit,
            args.case_sensitive, args.include_bare,
        )
    if args.cmd == "todos":
        return db.cmd_todos(args.vault, args.marker, args.page, args.limit)
    if args.cmd == "view":
        return view.cmd_view(args.name, args.vault)
    if args.cmd == "tui":
        return tui.cmd_tui(args.vault, args.theme)
    return 2


if __name__ == "__main__":
    sys.exit(main())
