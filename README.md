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
logseq parse <file>                          # → {page, blocks[]} JSON
logseq page  <file>                          # → just the page metadata
logseq journal <date> --in <dir>             # <date> = today | YYYY-MM-DD
logseq find-page <name> <dir> [<dir>...]     # → lines of "exact|substring\t<abs-path>"
```

See `SKILL.md` for the JSON contract.

## Run tests

```bash
.venv/bin/pytest -q
# parser + serializer + round-trip + CLI; ~1158 tests in ~1s
```

If `LOGSEQ_VAULT` env var or `/Users/bencode/Documents/bcd-new` exists, an additional 1122 round-trip tests run against that real vault to catch parser regressions.

## Status

Read-only MVP. Future stages: SQLite index, full-text search, backlinks, write commands. See the design document in `~/.claude/plans/` if you have access, or open an issue.

## Uninstall

```bash
rm -rf ~/.claude/skills/logseq-skill
```

(If you used the Development setup, also `rm -rf ~/work/logseq-skill`.)
