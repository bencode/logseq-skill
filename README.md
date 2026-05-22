# logseq-skill

A Claude Code skill that gives Claude an **LLM-powered query layer over your Logseq vault**. Fast cross-vault search, backlinks, todo aggregation, and ad-hoc questions — backed by SQLite + FTS5 + a CJK-aware tokenizer (`jieba`). Every result Claude shows you is one `Cmd+Click` away from the matching page in Logseq desktop.

```
You:    "找一下数学相关的笔记"
Claude: (calls `logseq search 数学`, formats results)

        - [我的专业书架](logseq://graph/notes?page=...) — 数学
        - [年度计划](logseq://graph/notes?page=...) — 英文写作和数学
        - [写作训练营](logseq://graph/notes?page=...) — 提到 [[数学]]
        ...

You:    Cmd+Click any of them → Logseq desktop jumps there.
```

## Why this exists

Logseq is great. **Its search isn't.**

Logseq stores everything in an in-memory DataScript DB rebuilt on each app start. That works fine at small scale, but past a few thousand notes you hit three failure modes:

1. **CJK search misses words.** Logseq tokenizes on whitespace/punctuation; Chinese has neither. Searching `数学` against a block containing `数学女孩` returns nothing — the whole CJK run is one opaque token.
2. **Startup-time indexing.** Open the app, immediately search → results are partial until the background indexer finishes (can take minutes for large vaults).
3. **No real query language.** "All my TODOs tagged with `[[trantor]]` from this month" isn't expressible in Logseq's UI.

This skill is the **query-layer fix**:

- **SQLite + FTS5** persistent index → sub-millisecond search across 10,000+ blocks. No startup rebuild.
- **`jieba` Chinese tokenizer** → `数学` correctly finds `数学女孩`. No false positives (`学生` does **not** match `数学生活`).
- **Composable CLI** → Claude (or `sqlite3`, or any tool) can express any cross-vault query.
- **`logseq://` URL bridge** → Claude finds; Logseq desktop displays. One click between them.

What this skill **does NOT** do: visual rendering, block editing, syncing, mobile, plugins. Those stay in Logseq desktop. This is the back-end you've been missing.

## Architecture in one diagram

```
┌─────────────┐
│ You (User)  │
└──────┬──────┘
       │ natural-language Q&A
       ↓
┌────────────────────────────────────────┐
│           Claude Code (LLM)             │
│   reads SKILL.md → calls CLI / Edit     │
└────┬───────────────────────────┬────────┘
     │ Bash                      │ Edit / Read
     ↓                           ↓
┌──────────────┐         ┌──────────────────┐
│  logseq CLI  │ ──read─→│ vault/*.md files │
│  + SQLite    │         │  (source truth)  │
│  + FTS5      │         └────────┬─────────┘
│  + jieba     │                  │
└──────┬───────┘                  │ Logseq desktop reads
       │ emits clickable          ↓
       │ logseq:// URLs    ┌──────────────────┐
       └──────────────────→│ Logseq Desktop UI│
                  ↑click   │ (visual reader)  │
                           └──────────────────┘
```

Three actors, clean handoff. Each owns what it's best at.

## Install

```bash
git clone https://github.com/bencode/logseq-skill ~/.claude/skills/logseq-skill
cd ~/.claude/skills/logseq-skill
uv venv && uv pip install -e ".[dev]"
```

Open a new Claude Code session — the skill auto-loads from `~/.claude/skills/logseq-skill/SKILL.md`.

**Prerequisites:**
- Python ≥ 3.11
- Logseq desktop installed (for the `logseq://` URL handoff)
- A terminal that renders clickable URLs: iTerm2, macOS Terminal.app, Windows Terminal, VS Code terminal, WezTerm, modern GNOME Terminal/Konsole all work.

## First use

1. Open Claude Code in any directory.
2. `/add-dir /path/to/your/logseq-vault` (the one containing `logseq/config.edn`).
3. Ask things like:
   - "今天的日志写了什么"
   - "找一下 trantor 相关的笔记"
   - "我现在有哪些 TODO，按页面分组"
   - "Week 20 那一页有啥总结"
   - "上个月我提到过 [[费曼]] 的 block 都列出来"

Claude detects the vault, indexes it on first use (incremental afterwards, ~30ms for a 1000-file vault), and returns results with `logseq://` URLs.

## CLI reference

The CLI is 9 commands. Claude invokes them; you can too:

```bash
# DB-backed (the actual value-add — Logseq doesn't index at this scale)
logseq index <vault> [--full]                # build/refresh SQLite + FTS5
logseq stats <vault>                          # → JSON: pages, blocks, refs, etc.
logseq search <query> <vault>                 # FTS5 + jieba CJK tokenization
logseq backlinks <name> <vault>               # who links to this page
logseq todos <vault> [--marker M]             # TODO/DOING/etc. aggregator

# Atomic file reads (LLM tool-call savings)
logseq parse <file>                           # → {page, blocks[]} JSON
logseq page <file>                            # → just page metadata
logseq journal <date> --in <vault>            # date = "today" | YYYY-MM-DD
logseq find-page <name> <dir>...              # case-insensitive name lookup
```

All commands emit JSON to stdout. See `SKILL.md` for the JSON contract and the `logseq://` URL convention.

**Deliberately not in the CLI:**

- `view` / pretty-rendering → use `logseq://` URL to open in Logseq desktop instead
- `capture` / `append` writes → Claude uses its `Edit` tool directly on the .md file (more flexible than a CLI wrapper)
- TUI browser → Logseq desktop is the visual UI

## CJK search quality

The killer feature, shown side-by-side:

| Query | Logseq desktop | This skill (jieba + FTS5) |
|-------|----------------|---------------------------|
| `数学` | 0 hits (CJK run is one token) | 5 hits incl. `数学女孩`, `数学物理` |
| `数学女孩` | needs exact match | 2 hits, no quotes needed |
| `学生` | finds `学生`, also wrongly finds `数学生活` | finds only real `学生` (jieba knows boundaries) |
| `feynman 物理` | partial | finds both terms |
| Latency on 30k blocks | seconds | < 5 ms |

`cut_for_search` mode (jieba's compound + sub-word emission) ensures both `物理` and `物理课` find blocks containing `物理课` — no recall loss.

## Run tests

```bash
.venv/bin/pytest -q
# ~1200 tests in ~2s
```

If `LOGSEQ_VAULT` env var (or a known default path) points to a real vault, an additional ~1100 round-trip tests run against every file in it to catch parser regressions on real-world content. This corpus check is the reason we know writes-via-Edit are safe — the parser↔serializer round-trips byte-identical on 1000+ real files.

## Lint

```bash
.venv/bin/ruff check .            # lint
.venv/bin/ruff check --fix .      # safe auto-fix
```

Enabled rules: pycodestyle, pyflakes, isort, pyupgrade, bugbear, simplify, ruff-specific. Relative imports inside the package are idiomatic; `assert False` is allowed in tests.

## Design philosophy

> **Let each tool do what it does best.**
>
> Logseq desktop owns visual reading + editing + sync.
> Claude owns search + analysis + cross-vault Q&A.
> The `logseq://` URL is the seam.

The skill aggressively rejects scope creep into Logseq's territory. During development we built a TUI browser, a write CLI, and a Rich-rendered page viewer — all ~3000 lines — then deleted them once we realized they duplicated capabilities Logseq desktop already does better. What's left is purely the layer Logseq itself is missing.

## Status

Stable. Production read API. CJK search certified on a 1000+ file real-world vault. Writes go through Claude's native `Read`/`Edit` tools (which round-trip-test clean on the same corpus).

**Possible future:**
- Block-ref backlinks (`((uuid))` → who embeds me)
- `logseq query <sql>` raw SQL escape hatch (today, advanced users `sqlite3 ~/.cache/logseq-skill/<hash>.db` directly)
- User-defined jieba dictionary for domain words (`trantor`, `pro-relation-select`, etc.)

## Uninstall

```bash
rm -rf ~/.claude/skills/logseq-skill
rm -rf ~/.cache/logseq-skill        # SQLite indexes
```

## License

MIT.
