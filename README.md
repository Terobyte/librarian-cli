<!-- mcp-name: io.github.Terobyte/librarian -->
# 📚 librarian

[![CI](https://github.com/Terobyte/librarian-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Terobyte/librarian-cli/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/librarian-cli)](https://pypi.org/project/librarian-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/librarian-cli)](https://pypi.org/project/librarian-cli/)
[![License](https://img.shields.io/pypi/l/librarian-cli)](LICENSE)
[![MCP registry](https://img.shields.io/badge/MCP_registry-io.github.Terobyte%2Flibrarian-6A5ACD)](https://registry.modelcontextprotocol.io/v0/servers?search=io.github.Terobyte/librarian)

Turn any ebook into clean, token-counted Markdown chapters — and let Claude read your
bookshelf over MCP. Deterministic RAG: no embeddings, no network, no API keys.

![demo](docs/assets/demo.gif)

Any input format — FB2, EPUB, DOCX, HTML, TXT/MD, text-layer PDF — becomes a directory of
clean chapters with token counts. No network, no LLM, no randomness: the same input always
produces byte-identical output.

## Install

```
uv tool install librarian-cli
# or: pipx install librarian-cli
```

Offline contract: install and runtime need no network (the tokenizer's vocabulary is
vendored in the package).

## Quick start

```
lib ingest examples/*.epub
lib list
lib find curiouser
lib get <book-id> --budget 3000
```

## Commands

| Command | Purpose |
|---------|---------|
| `lib ingest <files…> [--force] [--no-keep-source] [--config cfg.toml] [--verbose]` | Process books into the library; prints a file · id · status · score table. |
| `lib list [<book-id>]` | No argument — all books; with an id — that book's chapters (n, title, tokens, summary). |
| `lib get <book-id> <spec>` | Print chapters by range (`1-3,7`) to stdout. |
| `lib get <book-id> --budget N [--from K]` | Greedily print consecutive chapters from K while the token sum stays ≤ N. |
| `lib find <query> [--limit 10] [--book <id>] [--reindex] [--json]` | Full-text search across chapters and titles/authors library-wide (bm25, snippets, RU/EN stemming). |
| `lib info <book-id>` | JSON: book metadata + quality metrics. |
| `lib doctor [<book-id>]` | No id — books in review and broken directories; with id — that book's report. |
| `lib reingest --all [--config cfg.toml] [--verbose]` | Rebuild the library from `source/` with the current code/config. |
| `lib rm <book-id>` | Delete a book and rebuild the index. |
| `lib serve [--library <path>]` | Stdio MCP server over the library. |
| `lib verify "quote" [--book ID] [--json] [--limit N]` | Check a quote against one book or attribute it across the library. |

Library root: `--library <path>` (or the `LIB_HOME` env var, default `./library`). Data goes
to stdout, diagnostics to stderr. Exit codes: `0` success, `1` runtime error, `2` usage error.

## Give Claude your bookshelf

`librarian-cli` ships a built-in stdio MCP server with 6 read-only tools — `list_books`,
`list_chapters`, `find`, `get_chapters`, `book_info`, `verify_quote` — so Claude can browse
the catalog, search it, pull chapters under a token budget, and check its own quotes against
the source on its own: deterministic RAG with no embeddings, no network, and no API keys.

Claude Code:

```
claude mcp add librarian --env LIB_HOME=$HOME/books -- uvx librarian-cli
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "librarian": {
      "command": "uvx",
      "args": ["librarian-cli"],
      "env": { "LIB_HOME": "/path/to/books" }
    }
  }
}
```

## Verify quotes

*An MCP server that catches Claude misquoting your books.*

`lib verify "quote"` checks whether a quote actually appears in your library, verbatim —
punctuation, case, ё/е, and markdown formatting don't count. Two modes:

- **Book mode** (`--book <id>`): full scan of one book — "does this book actually say
  this?" Works without the search index.
- **Shelf mode** (no `--book`): attribution across the whole library via FTS5 candidates —
  "which book is this from?" The quote needs at least 5 significant words (stop words
  don't count), or the check is skipped with `verdict: null`.

```
lib verify "Рукописи не горят" --book bulgakov-master-i-margarita
lib verify "рукописи не горят никогда"
```

| verdict | meaning |
|---------|---------|
| `exact` | matches after normalization (punctuation/case/ё/typography don't count) |
| `close` | similarity ≥ 0.95 — near-exact, differences shown as a word-diff |
| `distorted` | similarity ≥ 0.75 — the right place, but the quote is misremembered |
| `not_found` | similarity < 0.75 — nothing like it in the book/library |
| `null` | check wasn't run: empty quote, or a short quote without `--book` |

Exit codes (grep-style semantics, a deliberate departure from the project's usual
"`1` = runtime error" — see `docs/MILESTONES.md` deviation 38):

| exit | case | stdout |
|------|------|--------|
| 0 | `exact` / `close` — quote confirmed | full report / JSON |
| 1 | `distorted` / `not_found` — not confirmed | full report / JSON |
| 1 | runtime error (unknown book id, no search index, locked index) | empty |
| 2 | usage error: empty/short quote (`verdict: null`), `--limit < 1` | empty (message on stderr) |

Script discriminator: exit `1` with non-empty stdout means "checked, not confirmed"; exit
`1` with empty stdout means an error (diagnostics went to stderr instead). **Exit `0`
includes `close`** — a strict CI gate must check `verdict == "exact"` in the `--json`
output, not the exit code alone.

## Quality

Every book gets a score from five metrics (coverage, structure, garbage, encoding,
dehyphenation): `ok` (score ≥ 0.90, no hard triggers) — saved silently; `review`
(0.60 ≤ score < 0.90, or triggers present) — saved with a warning, details via
`lib doctor <id>`; `failed` (score < 0.60) — not saved. Scans and password-protected PDFs
honestly fail (OCR and DRM removal are out of scope).

## Determinism

The pipeline has no network access, no LLM calls, and no randomness — the same input file
always produces byte-identical output. That makes ingestion reproducible and cacheable, and
it's what makes `lib serve`'s RAG deterministic: no embeddings to drift, no model calls to
vary between runs.

## Limitations

- PDF: works well on typographically normal books; complex layouts may land in `review`.
- DRM is not circumvented; source legality is the user's responsibility.
- Networked filesystems (NFS/SMB) are not supported (the advisory lock isn't reliable there).
- MOBI/DJVU and text-less scans are not supported (v3 candidates: OCR, calibre).
- CLI messages are currently in Russian; English output is planned.
- `lib verify`: quotes spanning a chapter boundary are not supported (v1) — the best you'll
  get is `distorted` on one half.
- `lib verify`: `close` on a single-word replacement is realistic from ~150 characters of
  quote; shorter quotes with a replaced word honestly land in `distorted` — a third of a
  three-word quote really is a distortion.
- `lib verify` shelf mode (no `--book`) needs the FTS5 search index; book mode
  (`--book <id>`) works without it in the CLI. `lib serve` as a whole still requires FTS5 —
  it syncs the index at startup regardless of which tool gets called.
- `lib verify` in book mode scans the whole chapter text in pure Python; a long book can
  take a few seconds of CPU. The MCP tool runs it in a worker thread so it doesn't block
  the rest of the server.

## Русская версия

See [README.ru.md](README.ru.md) for the Russian documentation.
