---
name: logseq-skill
description: LLM-powered query layer for Logseq vaults. SQLite + FTS5 + jieba CJK tokenizer for sub-millisecond cross-vault search, backlinks, and TODO aggregation that Logseq desktop can't deliver at scale. Atomic file primitives (parse / page / journal / find-page) plus DB-backed queries (index / stats / search / backlinks / todos). All results are formatted as `logseq://` URLs so Cmd+Click opens the matching page directly in Logseq desktop. Trigger when the user mentions "logseq", "today's journal" / "今天日志", "find X notes" / "找 X 笔记", "in my notes" / "在我笔记里", searches for content, asks about TODOs/backlinks, or references a /add-dir'd directory containing logseq/config.edn. Writes go through Claude's Read/Edit tools directly on the .md files, not through this CLI.
allowed-tools: Bash, Read, Edit, Glob, Grep
---

# logseq-skill

A small CLI of atomic Logseq operations. You (Claude) compose them in response to user requests; no scenario is hardwired.

## CLI invocation

Throughout this skill, `logseq` refers to the venv binary inside the skill
install. For Claude Code's canonical install path that's
`~/.claude/skills/logseq-skill/.venv/bin/logseq`. For other agents (Codex,
Cursor, etc.) it's `<install-dir>/.venv/bin/logseq` — wherever the user
cloned the repo. Use the absolute path when running Bash commands; the
venv binary is not on global PATH.

## 1. Find a Logseq directory

A Logseq directory is one that contains `logseq/config.edn`. Check the user's working directories (the ones they `/add-dir`'d):

```bash
ls /path/to/dir/logseq/config.edn
```

If exactly one matches, use it. If multiple, ask the user which. If none, ask the user where their notes live.

Remember the path within the conversation — don't re-detect for every call.

## 1.2. Always link page/block results as Logseq desktop URLs

When you show the user a list of pages, blocks, or search hits, **format every reference as a clickable `logseq://` URL** so the user can `Cmd+Click` in their terminal to jump straight to the visual Logseq desktop UI for that exact page or block. The user has confirmed: their primary visual reader is Logseq desktop; the CLI/Claude side handles search/analysis/writes, and the URL bridges the two.

URL templates (`<graph>` is the basename of the vault directory, e.g. `mynotes` for `~/Documents/mynotes`):

```
logseq://graph/<graph>?page=<url-encoded-page-name>
logseq://graph/<graph>?block-id=<block-uuid>
```

Use Python's `urllib.parse.quote` (or shell-side `python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))"`) to URL-encode page names — they often contain Chinese / spaces / `/` namespace separators.

Output as markdown links. Example after a `logseq search standup vault`:

```
- [Daily Standup](logseq://graph/mynotes?page=Daily%20Standup) — yesterday's blockers
- [Project Plan](logseq://graph/mynotes?page=Project%20Plan) — Q3 priorities
- [2026_05_22](logseq://graph/mynotes?page=2026_05_22) — today's journal, mentions [[Daily Standup]]
```

For block-specific results (when `search` / `backlinks` / `todos` returns a `uuid` field that's NOT an `auto:...` synthetic), use `?block-id=<uuid>` so Logseq opens directly to that block. For `auto:<hash>` uuids (parser-generated, not stored in the file), fall back to `?page=<page-name>`.

This is the default render style for all listing results — only skip if the user explicitly asks for raw JSON or a different format.

## 1.5. Keep the index fresh before DB-backed queries

The user usually edits in Logseq desktop while we work. Our index does
NOT auto-update — Logseq's writes don't notify us. **Before any
DB-backed query (`search`, `backlinks`, `todos`, `stats`), run
`logseq index <vault>` once.** It's incremental (~10-50ms when nothing
changed; ~1.3s on first build of a ~1000-file vault), so the cost is
invisible to the user but guarantees their latest edits are visible.

Skip this for commands that read files directly: `parse`, `page`,
`journal`, `find-page`. They bypass the index entirely.

For writes (your `Edit` / `Write` on the .md file directly — there's no
write CLI), run `logseq index <vault>` afterward so subsequent DB-backed
queries see the change. Same incremental cost.

Rough rule:
- Need fresh DB? → reindex first
- Reading a single file directly (parse / Read)? → no reindex
- After writing? → reindex once before the next DB-backed query

## 2. Atomic commands

All commands print JSON to stdout unless noted.

### `logseq parse <file>`
Parse any `.md` file into `{page, blocks[]}`. Use when you already know the file path.

### `logseq page <file>`
Same as parse but only the `page` object (cheaper for metadata-only queries).

### `logseq journal <date> --in <dir>`
- `<date>` is `today` or `YYYY-MM-DD`
- `--in` is the Logseq directory (required, no default)
- Resolves to `<dir>/journals/YYYY_MM_DD.md` and parses it
- Exit 1 if the file doesn't exist; exit 2 if `<date>` is malformed

### `logseq find-page <name> <dir> [<dir>...] [--non-empty]`
Find page files by name in one or more directories (recursive `*.md` scan).
- Exact lowercase match (`Path.stem.lower() == name.lower()`) is preferred
- If no exact match, falls back to substring (`name.lower() in stem.lower()`)
- Output: one match per line, `<kind>\t<absolute-path>`, where `<kind>` is `exact` or `substring`
- `--non-empty` filters out pages with zero blocks (common Logseq placeholders auto-created by clicking `[[X]]` but never written)
- Exit 0 if any match, 1 if none

### `logseq index <vault> [--full]`
Build or refresh the SQLite index for a vault (vault = directory with `logseq/config.edn`).
- Incremental by default: only re-parses files whose mtime+size changed; drops rows for deleted files
- `--full` wipes the DB and rebuilds from scratch atomically (writes to `<db>.tmp`, swaps on success)
- Vault path is canonicalized (`expanduser().resolve()`) — same vault via relative, absolute, symlinked, or `..`-laden spelling all hit the same DB
- DB path: `~/.cache/logseq-skill/<sha1(canonical_vault_path)[:16]>.db`
- Output: JSON `{scanned, skipped, reindexed, deleted, errors, auto_rebuilt, elapsed_ms}`
- `errors` counts files that failed to parse (non-UTF-8 etc.) plus blocks skipped due to cross-file `id::` duplication. Non-zero `errors` does not abort the run — surviving files/blocks are indexed; per-occurrence details are logged to stderr (`warn: ...` lines)
- `auto_rebuilt: true` means the index was silently rebuilt from scratch because the existing cache DB was corrupt or had a stale schema version (see "Confirm before rebuild" below)
- Exit code 2 with stderr message if `<vault>` is not a Logseq vault
- Real-world: ~1300ms for 1100 files full / ~25ms when nothing changed

### Confirm before rebuild

The cache DB is purely derived (vault is the source of truth), so a rebuild loses no data and costs only ~1.3s of local CPU — no LLM/API spend. Still, before triggering anything that may rebuild, **first call `logseq stats <vault>` and inspect the result**:

- `valid: false` → DB file is corrupt. Tell the user, ask permission, then `logseq index <vault>` (which will auto-rebuild).
- `schema_outdated: true` → DB was written by an older skill version. Tell the user "the index format changed in this version, need to rebuild from the vault (~1.3s, no data loss)", ask permission, then `logseq index <vault>`.
- `valid: true, schema_outdated: false` → safe to use the index directly or do an incremental refresh.

`logseq index` will still auto-rebuild on corrupt/mismatched DB even if you don't pre-check, but you'll surprise the user with a 1.3s run instead of a 25ms incremental. Pre-checking + asking is the polite path.

### `logseq stats <vault>`
Show index status without rebuilding. Output: JSON `{db_path, db_exists, valid, pages, blocks, refs, db_size_bytes, last_index_ts, vault_path, schema_version, expected_schema_version, schema_outdated}`. On corrupt DB returns `{db_exists: true, valid: false, error: "..."}`.

### `logseq search <query> <vault> [--limit N] [--snippet] [--min-len N]`
FTS5 full-text search across all blocks in the vault.
- Default `--limit 20`
- `<query>` is an FTS5 MATCH expression: bare word, `"exact phrase"`, `term1 AND term2`, `term1 OR term2`, `prefix*`
- Results ranked by BM25 relevance (lower score = better)
- `--snippet` adds a `snippet` field per result with `«matched»` highlights and `...` context truncation
- `--min-len N` filters out blocks shorter than N chars. **Crucial knob for tag-heavy vaults**: BM25 favors short blocks (high term-frequency / length ratio), so bare `[[X]]` tag-blocks often dominate without this filter. Try `--min-len 25` for "substantive" results.
- **CJK is tokenized by `jieba`** in search mode (`cut_for_search`): the index stores compound words and their constituent sub-words, so `数学` correctly finds blocks containing `数学女孩`, AND `学生` correctly does NOT match `数学生活` (jieba splits as 数学/生活, not 数/学/生/活). User queries are jieba-tokenized the same way; FTS5 operators (`AND` / `OR` / `NOT` / `"..."` phrases) pass through unchanged.
- Output: JSON array `[{page, uuid, content, snippet?}, ...]`
- Exit codes: 0 success (even with empty results); 3 if no index for vault; 4 if index stale

### `logseq backlinks <name> <vault> [--limit N] [--case-sensitive] [--include-bare]`
Find blocks linking to a given page (`[[name]]` references).
- Default `--limit 50`
- Case-insensitive by default (matches `[[MyProject]]` when querying `myproject`); pass `--case-sensitive` for exact match
- **Bare tag-only blocks** (content is literally just `[[name]]`, a common Logseq idiom for daily status markers) are filtered out by default to surface substantive backlinks. Pass `--include-bare` to see them too.
- Only page refs (`kind='page'`); block refs (`((uuid))`) not yet covered
- Output: JSON array `[{page, uuid, content}, ...]`
- Exit codes: same as `search`

### Reading a page — emit a `logseq://` URL (§1.2), don't print content here

We **deliberately have no `view` / pretty-render CLI**. To show the user a page, generate a markdown link with `logseq://graph/<graph>?page=<urlencoded-name>` and let them `Cmd+Click` to land in Logseq desktop's full visual UI. See §1.2 for the exact URL templates and example output. For programmatic reads (parsing structure), use `logseq parse <file>` or just `Read` the .md file.

### Writes — use Edit tool directly, not a CLI command

We **deliberately have no `capture`/`append` CLI**. LLM (you, Claude) handle writes natively via the `Edit` / `Write` tools — more flexible than a CLI wrapper (you can insert in the middle of a file, edit existing blocks, construct nested structures, etc.).

When the user says "remind me to X" or "add Y to my notes":
1. **For today's journal**: `Read` `<vault>/journals/YYYY_MM_DD.md` (create if missing), `Edit` to append the new bullet line, then `logseq index <vault>` to refresh the index. **Format**: `- TODO write the blog post` (tab-indent only if nested; if the existing file doesn't end with `\n`, prepend `\n` to your new line to avoid splicing onto a previous naked `\t-` bullet).
2. **For an existing named page**: same pattern on `<vault>/pages/<Name>.md`.

### `logseq todos <vault> [--marker M] [--page P] [--limit N]`
List blocks with a task marker.
- Default `--marker TODO`; common alternatives: `DOING`, `DONE`, `NOW`, `LATER`, `WAITING`, `CANCELLED`
- Default `--limit 50`
- Optional `--page <name>` to restrict to one page
- Output: JSON array `[{page, uuid, content}, ...]`
- Exit codes: same as `search`

## 3. JSON contract (output of `parse` and `journal`)

```jsonc
{
  "page": {
    "name": "claudecode使用",          // lowercase canonical (Logseq :block/name)
    "title": "ClaudeCode使用",         // original case (Logseq :block/title)
    "type": "page" | "journal",
    "file_path": "/abs/path/.../Foo.md",
    "properties": {"alias": "..."},
    "aliases": ["foo", "bar baz"],     // parsed from `alias::` property
    "namespace_parent": null,           // "foo" if page is "foo/bar"
    "journal_day": 20260521 | null,     // YYYYMMDD for journals
    "block_count": 7                     // len(blocks); 0 = Logseq placeholder page
  },
  "blocks": [
    {
      "uuid": "auto:f5a5d3dd8358",     // synthesized when no `id::`; otherwise the explicit uuid
      "has_explicit_id": false,
      "page": "claudecode使用",
      "parent_uuid": null,
      "sibling_order": 0,
      "depth": 0,
      "marker": "TODO" | null,         // first-class; not embedded in content
      "content": "写文档",              // marker is already stripped off
      "properties": {},
      "refs": [
        {"kind": "page" | "tag" | "block" | "embed", "target": "...", "raw": "[[...]]"}
      ],
      "line_start": 0,
      "line_end": 0
    }
  ]
}
```

Notes:
- Page references keep their original `[[brackets]]` and `((uuid))` syntax in `raw` — don't translate to markdown links when showing the user; they think in Logseq syntax
- `parent_uuid` lets you reconstruct the tree; `sibling_order` orders children
- Block references (`((uuid))`) point at *other blocks* — to resolve, search for a block with that `uuid` in the index (future stage) or via `find-page`-then-`parse` for a specific page
- Backlinks are not a stored field on blocks themselves; query them via `logseq backlinks <name> <vault>` (uses the `refs` table maintained by `logseq index`)

## 4. Composition examples (not scripts — adapt to context)

```bash
# User: "看一下今天的日志"
logseq journal today --in /path/to/logseq-dir
# → summarize/relay the JSON

# User: "费曼那一页有啥"
logseq find-page 费曼 /path/to/logseq-dir
# → take first match path, then:
logseq parse /path/.../Feynman.md

# User: "搜一下我笔记里的 X"
logseq stats /path/to/vault           # pre-check: index built + not stale?
logseq search 'X' /path/to/vault      # → array of {page, uuid, content}

# User: "谁链接到我的 myproject 这一页"
logseq backlinks myproject /path/to/vault

# User: "我现在有哪些 TODO"
logseq todos /path/to/vault --limit 20
```

## 5. Scope & Non-goals

**This skill is the LLM-powered query layer for Logseq vaults — not a Logseq replacement.** Clear division of labor:

| Task | Tool |
|------|------|
| Cross-vault search, backlinks, TODO aggregation, ad-hoc SQL queries | **This skill** (via Claude) |
| Reading a page visually, editing notes, drawing whiteboards, syncing | **Logseq desktop** (open via `logseq://` URL — §1.2) |
| Quick file-level edit (append a line, fix a typo) | **Claude's Read/Edit tools** directly on the .md file |

What we DO:
- ✅ SQLite + FTS5 index with jieba CJK tokenization (`index`, `stats`)
- ✅ Full-text search across 1000+ files at sub-millisecond latency (`search`)
- ✅ Page-ref backlinks (`backlinks`)
- ✅ TODO/DOING aggregation across vault (`todos`)
- ✅ Single-page structured parsing (`parse`, `page`, `journal`, `find-page`)
- ✅ `logseq://` URL emission so Claude's findings are one Cmd+Click away from Logseq desktop's visual UI

What we explicitly DON'T do (by design — Logseq desktop does these well):
- No TUI / no terminal-side block editing UI
- No write CLI — Claude uses Read+Edit on the .md files; user does heavier editing in Logseq desktop
- No markdown rendering server / browser preview
- No sync, no whiteboard, no graph view, no editor

Possible future:
- Block-ref backlinks (who embeds `((uuid))`)
- `logseq query <sql>` raw SQL escape hatch — currently advanced users `sqlite3 ~/.cache/logseq-skill/<hash>.db`
