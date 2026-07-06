from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from librarian.catalog import read_book, rebuild_index
from librarian.config import load_config
from librarian.emit import library_lock, recover
from librarian.errors import LibError
from librarian.pipeline import run_ingest

app = typer.Typer(add_completion=False, no_args_is_help=True)
_state: dict = {"library": None}
_err = Console(stderr=True)


def _lib_root() -> Path:
    if _state["library"]:
        return _state["library"]
    return Path(os.environ.get("LIB_HOME") or "./library")


@app.callback()
def _main(library: Path | None = typer.Option(None, "--library",
                                              help="корень библиотеки")) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stderr.reconfigure(encoding="utf-8", newline="\n")
    _state["library"] = library


def parse_spec(spec: str, n_max: int) -> list[int]:
    import re
    if not re.fullmatch(r"\d+(-\d+)?(,\d+(-\d+)?)*", spec):
        raise ValueError(f"неверный формат диапазона: {spec}")
    nums: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        n, m = int(a), int(b or a)
        if m < n or n < 1 or m > n_max:
            raise ValueError(f"диапазон {part} вне 1..{n_max}")
        nums.extend(range(n, m + 1))
    return nums


@app.command()
def ingest(paths: list[Path],
           force: bool = typer.Option(False, "--force"),
           no_keep_source: bool = typer.Option(False, "--no-keep-source"),
           config: Path | None = typer.Option(None, "--config"),
           verbose: bool = typer.Option(False, "--verbose")) -> None:
    cfg = load_config(config, keep_source=not no_keep_source)
    outcomes = run_ingest(paths, cfg, _lib_root(), force=force)
    table = Table("файл", "id", "статус", "score")
    for o in outcomes:
        table.add_row(o.path.name, o.book_id or "—", o.status,
                      f"{o.score:.2f}" if o.score is not None else "—")
        if o.message:
            _err.print(f"  {o.path.name}: {o.message}")
    _err.print(table)
    if any(o.status == "failed" for o in outcomes):
        raise typer.Exit(1)


@app.command("list")
def list_cmd(book_id: str = typer.Argument(None)) -> None:
    out = Console()
    try:
        if book_id is None:
            import json
            idx_path = _lib_root() / "index.json"
            books = (json.loads(idx_path.read_text(encoding="utf-8"))["books"]
                     if idx_path.is_file() else [])
            t = Table("id", "автор", "название", "глав", "токенов", "статус")
            for b in books:
                t.add_row(b["id"], b["author"] or "", b["title"] or "",
                          str(b["chapters"]), str(b["total_tokens"]), b["status"])
            out.print(t)
        else:
            book = read_book(_lib_root(), book_id)
            t = Table("n", "заголовок", "токенов", "summary", title=book_id)
            for ch in book["chapters"]:
                t.add_row(str(ch["n"]), ch["title"], str(ch["tokens"]),
                          (ch["summary"] or "")[:80])
            out.print(t)
    except LibError as e:
        _err.print(str(e))
        raise typer.Exit(1)


@app.command()
def get(book_id: str, spec: str) -> None:
    try:
        book = read_book(_lib_root(), book_id)
        nums = parse_spec(spec, len(book["chapters"]))
        by_n = {ch["n"]: ch for ch in book["chapters"]}
        texts = [(_lib_root() / book_id / by_n[n]["file"])
                 .read_text(encoding="utf-8") for n in nums]
        sys.stdout.write("\n\n".join(t.rstrip("\n") for t in texts) + "\n")
    except (LibError, ValueError) as e:
        _err.print(str(e))
        raise typer.Exit(1)


@app.command()
def info(book_id: str) -> None:
    import json
    try:
        book = read_book(_lib_root(), book_id)
        report_path = _lib_root() / book_id / "report.json"
        report = (json.loads(report_path.read_text(encoding="utf-8"))
                  if report_path.is_file() else {})
        payload = {"book": book,
                   "metrics": report.get("metrics", {}),
                   "subscores": report.get("subscores", {}),
                   "score": report.get("score"),
                   "hard_triggers": report.get("hard_triggers", [])}
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2,
                                    sort_keys=True) + "\n")
    except LibError as e:
        _err.print(str(e))
        raise typer.Exit(1)


@app.command()
def rm(book_id: str) -> None:
    lib = _lib_root()
    cfg = load_config(None)
    try:
        with library_lock(lib, cfg.general.lock_timeout_s):
            recover(lib)
            target = lib / book_id
            if not (target / "book.json").is_file():
                raise LibError(f"книга «{book_id}» не найдена")
            shutil.rmtree(target)
            rebuild_index(lib)
    except LibError as e:
        _err.print(str(e))
        raise typer.Exit(1)
