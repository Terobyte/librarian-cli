# examples/

Two small public-domain books from [Project Gutenberg](https://www.gutenberg.org/), used
for the quick start and the demo GIF.

| File | Source | Provenance |
|------|--------|------------|
| `alice-in-wonderland.epub` | [Alice's Adventures in Wonderland](https://www.gutenberg.org/ebooks/11), Lewis Carroll | Project Gutenberg #11 — public domain in the United States |
| `the-yellow-wallpaper.epub` | [The Yellow Wallpaper](https://www.gutenberg.org/ebooks/1952), Charlotte Perkins Gilman | Project Gutenberg #1952 — public domain in the United States |

## Try it

```
lib ingest examples/*.epub
lib list
lib find curiouser
lib get <alice-id> --budget 3000
```
