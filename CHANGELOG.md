# Changelog

## 0.2.0 — 2026-07-10

- `lib verify "quote" [--book ID] [--json] [--limit N]`: catches misquoted book text,
  deterministically, no LLM. Book mode (`--book`) does a full scan of one book; shelf mode
  (no `--book`) attributes the quote across the library via FTS5 candidates.
- Verdicts `exact` / `close` / `distorted` / `not_found` / `null`, a word-level diff against
  the source for `close`/`distorted`, and grep-style exit codes with a script discriminator
  (exit 1 with empty stdout = error; exit 1 with output = "checked, not confirmed").
- 6th MCP tool, `verify_quote` — runs in a worker thread so a full book scan doesn't block
  the stdio server; all 6 tool descriptions are now in English (previously Russian).

## 0.1.1 — 2026-07-08

- Fix the `mcp-name` ownership marker case (`io.github.Terobyte/librarian`) so the MCP
  registry can validate the PyPI package; shorter registry description. No code changes.

## 0.1.0 — 2026-07-08

- Deterministic pipeline turning FB2, EPUB, DOCX, HTML, TXT/MD, and text-layer PDF into
  clean, token-counted Markdown chapters — byte-identical output for identical input.
- Quality gate: five metrics (coverage, structure, garbage, encoding, dehyphenation) score
  every book into `ok` / `review` / `failed`, with `lib doctor` for diagnostics.
- `lib find`: FTS5 full-text search across chapters, titles, and authors, with RU/EN
  stemming and JSON output.
- Built-in MCP server (`lib serve` / `librarian-cli`): 5 read-only tools over the same
  reader core, so Claude can browse, search, and pull chapters under a token budget —
  deterministic RAG with no embeddings, no network, no API keys.
- Offline-vendored o200k_base tokenizer — no network calls at install or runtime.
- CLI: `ingest · list · get (spec | --budget) · find · info · doctor · reingest · rm · serve`.
