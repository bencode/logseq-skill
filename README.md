# logseq-skill

A Claude Code skill for read-only operations over a Logseq directory. Parses `.md` files into structured JSON (block tree, refs, properties, marker, journal metadata) so Claude can answer questions about your notes.

Atomic primitives: `parse` / `page` / `journal` / `find-page`. The LLM composes them — there are no hardcoded scenarios.

## Install

The canonical Claude Code skill location is `~/.claude/skills/<name>/`. Clone directly there:

```bash
git clone git@github.com:bencode/logseq-skill.git ~/.claude/skills/logseq-skill
cd ~/.claude/skills/logseq-skill
uv venv
uv pip install -e ".[dev]"
```

Open a new Claude Code session and the skill becomes available — Claude will detect `~/.claude/skills/logseq-skill/SKILL.md` and follow its instructions.

## Verify

```bash
~/.claude/skills/logseq-skill/.venv/bin/logseq parse \
  ~/.claude/skills/logseq-skill/tests/fixtures/simple.md
# should print {"page": ..., "blocks": [...]}
```

## Development

To hack on the skill itself, clone anywhere and symlink:

```bash
git clone git@github.com:bencode/logseq-skill.git ~/work/logseq-skill
cd ~/work/logseq-skill
uv venv && uv pip install -e ".[dev]"
ln -s "$(pwd)" ~/.claude/skills/logseq-skill
```

This keeps the dev tree separate from the "installed" skill location. (`~/.claude/skills/` officially expects a real directory; symlinking works in practice but isn't documented.)

## Use in Claude Code

1. Open Claude Code in any directory
2. `/add-dir /path/to/your/logseq/notes` (the directory containing `logseq/config.edn`)
3. Ask things like:
   - "今天的日志写了什么？"
   - "找一下 [[X]] 这一页"
   - "把 Y 这一页的待办事项列出来"

Claude will detect the Logseq directory among your working dirs and call the CLI behind the scenes.

## CLI reference

```
# Atomic file reads (LLM convenience — saves tool calls):
logseq parse <file>                          # → {page, blocks[]} JSON
logseq page  <file>                          # → just the page metadata
logseq journal <date> --in <dir>             # <date> = today | YYYY-MM-DD
logseq find-page <name> <dir> [<dir>...]     # → "exact|substring\t<abs-path>"

# DB-backed (the actual value-add — Logseq itself has no DB):
logseq index <vault> [--full]                # build/refresh SQLite + FTS5 index
logseq stats <vault>                         # → JSON {pages, blocks, refs, ...}
logseq search <query> <vault>                # FTS5 + jieba CJK tokenization
logseq backlinks <name> <vault>              # who links to this page
logseq todos <vault>                         # TODO/DOING aggregator
```

See `SKILL.md` for the JSON contract and the `logseq://` URL convention that lets Claude's results land directly in Logseq desktop with a `Cmd+Click`.

**Not in this CLI**: visual rendering, editing, capture. Logseq desktop covers reading + writing (Cmd+Click on the URLs Claude emits); LLM `Edit` covers ad-hoc file edits. This skill stays scoped to "the LLM-powered query layer".

## Run tests

```bash
.venv/bin/pytest -q
# parser + serializer + round-trip + CLI; ~1200 tests in ~2s
```

If `LOGSEQ_VAULT` env var or `/Users/bencode/Documents/bcd-new` exists, an additional ~1100 round-trip tests run against that real vault to catch parser regressions.

## Lint

Ruff is the only lint/format tool (config in `pyproject.toml [tool.ruff]`).

```bash
.venv/bin/ruff check .              # lint
.venv/bin/ruff check --fix .        # auto-fix safe issues
.venv/bin/ruff format .             # format (opinionated; not yet adopted)
```

Enabled rule families: pycodestyle (E/W), pyflakes (F), isort (I), pyupgrade (UP), bugbear (B), simplify (SIM), ruff-specific (RUF). `TID252` (relative-import warning) is intentionally not enabled — relative imports inside a package are idiomatic. `assert False` is per-file-allowed in `tests/*`.

## Status

DB-backed read API + jieba CJK tokenizer + atomic file primitives. Visual reading and edits delegate to Logseq desktop / LLM Edit respectively.

## Uninstall

```bash
rm -rf ~/.claude/skills/logseq-skill
```

(If you used the Development setup, also `rm -rf ~/work/logseq-skill`.)
