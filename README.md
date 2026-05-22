# logseq-skill

A Claude Code skill (also usable by Codex / Cursor / any agent that can run a CLI and read a SKILL file) that gives an LLM agent a **fast query layer over a Logseq vault**: SQLite + FTS5 + `jieba` CJK tokenizer, plus a `logseq://` URL convention so every result is one Cmd+Click away from opening in Logseq desktop.

Logseq itself has no persistent search index and tokenizes CJK as opaque runs, so anything past a few thousand notes slows down or stops finding things. This skill is that missing layer.

## Install

For Claude Code (canonical skill location):

```bash
git clone https://github.com/bencode/logseq-skill ~/.claude/skills/logseq-skill
cd ~/.claude/skills/logseq-skill
uv venv && uv pip install -e .
```

For Codex / Cursor / other agents: clone anywhere and point your agent's instruction file at `<repo>/SKILL.md`. The CLI binary lives at `<repo>/.venv/bin/logseq` after install.

**Requires**: Python ≥ 3.11. Logseq desktop is optional but recommended (for the `logseq://` URL handoff).

## CLI

```bash
# DB-backed (the value-add — runs in milliseconds, not seconds)
logseq index <vault>                     # build / refresh SQLite + FTS5
logseq stats <vault>                     # health + counts
logseq search <query> <vault>            # FTS5 + jieba CJK tokenization
logseq backlinks <name> <vault>          # who links to this page
logseq todos <vault> [--marker M]        # TODO / DOING aggregator

# Atomic file reads (LLM tool-call savings)
logseq parse <file>                      # → {page, blocks[]} JSON
logseq page <file>                       # → page metadata only
logseq journal <date> --in <vault>       # date = "today" | YYYY-MM-DD
logseq find-page <name> <dir>...         # case-insensitive name lookup
```

All output is JSON on stdout. Exit codes and the full JSON contract: `SKILL.md`.

**Not in the CLI** (intentional):
- No `view` / pretty-render — emit `logseq://graph/<vault>?page=<encoded-name>` and let Cmd+Click open Logseq desktop.
- No `capture` / `append` writes — agents use their native `Edit` / `Write` tool on the .md file directly.

## Agent quickstart

Once installed and the user `/add-dir`'d a vault containing `logseq/config.edn`:

1. Run `logseq index <vault>` once per session (incremental, ~30 ms on a 1000-file vault if unchanged).
2. For "find X" / "show me X" requests, call `logseq search` / `backlinks` / `find-page` and format results as `[title](logseq://graph/<basename>?page=<urlencoded-name>)` markdown links.
3. For writes ("remind me to ..." / "add X to today"), use `Read` + `Edit` on `<vault>/journals/YYYY_MM_DD.md`. Then re-run `logseq index` so the new content is searchable.
4. For "summarize X" / analysis, `Read` the .md file directly.

Full agent contract: `SKILL.md`.

## Tests

```bash
.venv/bin/pytest -q          # ~1200 tests in ~2s
.venv/bin/ruff check .       # lint
```

If `LOGSEQ_VAULT` env var points to a real Logseq vault, ~1100 additional parser round-trip tests run against every `.md` file in it — the corpus regression that backs the "writes-via-Edit are safe" claim.

## Uninstall

```bash
rm -rf ~/.claude/skills/logseq-skill
rm -rf ~/.cache/logseq-skill   # SQLite indexes
```

## License

MIT.
