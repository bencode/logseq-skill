"""Jieba-based tokenization for FTS5 indexing.

Why this exists: SQLite FTS5's built-in `unicode61` tokenizer is naive
for CJK — it treats each codepoint as a token. Searching `学生` then
spuriously matches `数学生活` because the chars `学` `生` happen to be
adjacent. Jieba understands word boundaries (`数学/生活`, `学生/时代`)
so we get both higher recall AND no false positives.

The trick: tokenize each block's content with jieba into space-separated
words, store as a separate column, and let FTS5 index that column with
its standard `unicode61` tokenizer — which now sees spaces between
Chinese "words" and indexes one term per word.

At search time, tokenize the user's query the same way; FTS5 then
matches `学生` against the indexed token `学生`, not against arbitrary
character spans."""

from __future__ import annotations

import jieba

# Load the dictionary once at import (lazy on first call would also work
# but eager keeps first query latency predictable). ~300ms one-time cost.
jieba.initialize()


def tokenize_for_index(text: str) -> str:
    """Jieba-tokenize block content for FTS5 storage. Output is a single
    space-separated string. FTS5's unicode61 tokenizer will then split
    on these spaces, giving us one FTS5 term per jieba word.

    Uses `cut_for_search` — search-mode tokenization that emits both the
    compound word AND its constituent sub-words. E.g. `物理课` → `物理
    物理课`, so the index matches both `物理` and `物理课` queries.

    Importantly, `cut_for_search` does NOT emit invalid character spans
    like `学生` inside `数学生活` (it splits as `数学 生活`), so the
    classic false-positive is still prevented.

    Non-CJK content (ASCII words, numbers, punctuation) passes through
    largely unchanged."""
    if not text:
        return ""
    return " ".join(t for t in jieba.cut_for_search(text) if t.strip())


def tokenize_query(query: str) -> str:
    """Tokenize a user-supplied search query the same way as the index.

    Preserves FTS5 operators / phrase quotes that the user explicitly
    typed: if the query contains `"`, `(`, ` AND `, ` OR `, ` NOT `, or
    `NEAR`, treat it as an advanced FTS5 query — tokenize only the
    bare terms.

    For the common case (just words / Chinese), jieba split and
    space-join. FTS5 will then implicit-AND the tokens (all must be
    present somewhere in a matching block)."""
    if not query.strip():
        return ""
    if _has_fts_operators(query):
        # Advanced query — try to tokenize each unquoted segment.
        # For simplicity, only tokenize content inside `"..."` phrase
        # quotes; pass operators through untouched.
        return _tokenize_advanced(query)
    return tokenize_for_index(query)


def _has_fts_operators(q: str) -> bool:
    if '"' in q or "(" in q:
        return True
    return any(op in q for op in (" AND ", " OR ", " NOT ", " NEAR "))


def _tokenize_advanced(query: str) -> str:
    """Re-tokenize phrases inside `"..."` but leave operators alone.

    Defensive on malformed quoting: if the number of `"` characters is
    odd, the user has an unmatched quote — fall back to "treat the whole
    thing as plain text", which (a) avoids emitting malformed FTS5 syntax
    and (b) still gives the user some result for what they typed."""
    if query.count('"') % 2 != 0:
        # Strip the orphan quote(s) and tokenize as plain. Better than
        # passing a syntactically-broken query to FTS5.
        return tokenize_for_index(query.replace('"', ""))
    out: list[str] = []
    i = 0
    while i < len(query):
        if query[i] == '"':
            j = query.find('"', i + 1)
            # j != -1 guaranteed by the even-count precondition above
            phrase = query[i + 1 : j]
            tokenized = tokenize_for_index(phrase)
            out.append(f'"{tokenized}"')
            i = j + 1
        else:
            out.append(query[i])
            i += 1
    return "".join(out)
