---
name: logseq-skill
description: Atomic read primitives over a Logseq directory. Parse a single .md file, find page files by name, fetch a journal by date. CLI outputs structured JSON; the model composes calls. Trigger when the user mentions "logseq", "today's journal" / "今天日志", "find X notes" / "找 X 笔记", "in my notes" / "在我笔记里", or asks about content after they've /add-dir'd a directory containing logseq/config.edn. This skill is read-only — no rendering, no writes, no full-text index (those are future stages).
allowed-tools: Bash, Read
---

# logseq-skill

A small CLI of atomic Logseq operations. You (Claude) compose them in response to user requests; no scenario is hardwired.

## CLI invocation

Throughout this skill, `logseq` refers to the absolute path
`~/.claude/skills/logseq-skill/.venv/bin/logseq`. Use that absolute path
when running Bash commands — the venv binary is not on global PATH.

## 1. Find a Logseq directory

A Logseq directory is one that contains `logseq/config.edn`. Check the user's working directories (the ones they `/add-dir`'d):

```bash
ls /path/to/dir/logseq/config.edn
```

If exactly one matches, use it. If multiple, ask the user which. If none, ask the user where their notes live.

Remember the path within the conversation — don't re-detect for every call.

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

### `logseq find-page <name> <dir> [<dir>...]`
Find page files by name in one or more directories (recursive `*.md` scan).
- Exact lowercase match (`Path.stem.lower() == name.lower()`) is preferred
- If no exact match, falls back to substring (`name.lower() in stem.lower()`)
- Output: one match per line, `<kind>\t<absolute-path>`, where `<kind>` is `exact` or `substring`
- Exit 0 if any match, 1 if none

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
    "journal_day": 20260521 | null      // YYYYMMDD for journals
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
- Backlinks are NOT a stored field — they need an index (future stage 4). For now, tell the user it's not yet supported, or grep manually

## 4. Composition examples (not scripts — adapt to context)

```bash
# User: "看一下今天的日志"
logseq journal today --in /path/to/logseq-dir
# → summarize/relay the JSON

# User: "费曼那一页有啥"
logseq find-page 费曼 /path/to/logseq-dir
# → take first match path, then:
logseq parse /path/.../Feynman.md

# User: "搜一下我笔记里的 X"  (no search yet)
# Tell user search is a future feature; meanwhile fall back to:
grep -rln 'X' /path/to/logseq-dir/{journals,pages}/
```

## 5. What this skill explicitly does NOT do (yet)

- ❌ Full-text search → stage 4 (`logseq search`)
- ❌ Backlinks → stage 4 (`logseq backlinks`)
- ❌ Append / edit / delete blocks → stages 5-6
- ❌ Markdown rendering → external browser component (planned)
- ❌ SQLite index / persistent cache → stage 3

When asked for any of these, say so directly. Don't fake it by stitching together unreliable greps unless the user explicitly accepts that.
