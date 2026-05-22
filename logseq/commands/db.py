from __future__ import annotations

import sys
from pathlib import Path

from .atomic import emit_json


def cmd_index(vault: str, full: bool) -> int:
    from ..index import reindex
    try:
        result = reindex(Path(vault), full=full)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    emit_json({
        "scanned": result.scanned,
        "skipped": result.skipped,
        "reindexed": result.reindexed,
        "deleted": result.deleted,
        "errors": result.errors,
        "auto_rebuilt": result.auto_rebuilt,
        "elapsed_ms": result.elapsed_ms,
    })
    return 0


def cmd_stats(vault: str) -> int:
    from ..stats import stats
    try:
        emit_json(stats(Path(vault)))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


def cmd_search(
    query: str, vault: str, limit: int, snippet: bool, min_len: int
) -> int:
    from ..queries import search
    return _run_query(
        lambda: search(
            Path(vault), query, limit=limit, snippet=snippet, min_len=min_len
        )
    )


def cmd_backlinks(
    name: str, vault: str, limit: int, case_sensitive: bool, include_bare: bool
) -> int:
    from ..queries import backlinks
    return _run_query(
        lambda: backlinks(
            Path(vault), name, limit=limit,
            case_sensitive=case_sensitive, include_bare=include_bare,
        )
    )


def cmd_todos(vault: str, marker: str, page: str | None, limit: int) -> int:
    from ..queries import todos
    return _run_query(
        lambda: todos(Path(vault), marker=marker, page=page, limit=limit)
    )


def _run_query(fn):
    from ..queries import IndexMissing, IndexStale
    try:
        emit_json(fn())
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
