<!-- mcp-name: io.github.terobyte/librarian -->
# librarian

[![CI](https://github.com/Terobyte/librarian-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Terobyte/librarian-cli/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/librarian-cli.svg)](https://pypi.org/project/librarian-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/librarian-cli.svg)](https://pypi.org/project/librarian-cli/)
[![License](https://img.shields.io/pypi/l/librarian-cli.svg)](LICENSE)

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

Library root: `--library <path>` (or the `LIB_HOME` env var, default `./library`). Data goes
to stdout, diagnostics to stderr. Exit codes: `0` success, `1` runtime error, `2` usage error.

## Give Claude your bookshelf

`librarian-cli` ships a built-in stdio MCP server with 5 read-only tools — `list_books`,
`list_chapters`, `find`, `get_chapters`, `book_info` — so Claude can browse the catalog,
search it, and pull chapters under a token budget on its own: deterministic RAG with no
embeddings, no network, and no API keys.

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

## Русская версия

See [README.ru.md](README.ru.md) for the Russian documentation.
