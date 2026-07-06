from __future__ import annotations

import re
import unicodedata
import zipfile
from pathlib import Path

import charset_normalizer

from librarian.errors import BrokenFileError, DetectError
from librarian.ir import Format

_SKIP = re.compile(r"(?:\s+|<\?.*?\?>|<!--.*?-->)", re.S)


def detect(path: Path) -> Format:
    with path.open("rb") as f:
        head = f.read(1024)
    if b"%PDF" in head:
        return Format.PDF
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return _detect_zip(path)
    tag = _first_significant_tag(path)
    if tag.startswith("<FictionBook"):
        return Format.FB2
    if tag.casefold().startswith(("<!doctype html", "<html")):
        return Format.HTML
    if path.suffix.casefold() in (".md", ".markdown") and _is_texty(path):
        return Format.MD
    if _is_texty(path):
        return Format.TXT
    raise DetectError(f"{path.name}: неизвестный формат")


def _detect_zip(path: Path) -> Format:
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if any(zi.flag_bits & 0x1 for zi in z.infolist()):
                raise BrokenFileError(f"{path.name}: зашифрованный zip")
            if "mimetype" in names and z.read("mimetype").strip() == b"application/epub+zip":
                return Format.EPUB
            if "word/document.xml" in names:
                return Format.DOCX
            fb2 = [n for n in names if n.casefold().endswith(".fb2") and not n.endswith("/")]
            if len(fb2) == 1:
                return Format.FB2
            if len(fb2) >= 2:
                raise DetectError(f"{path.name}: в архиве несколько .fb2")
            raise DetectError(f"{path.name}: zip неизвестного назначения")
    except zipfile.BadZipFile as e:
        raise BrokenFileError(f"{path.name}: битый zip: {e}") from None


def _first_significant_tag(path: Path) -> str:
    with path.open("rb") as f:
        data = f.read(4096)
    if data.startswith(b"\xef\xbb\xbf"):
        text = data[3:].decode("utf-8", errors="replace")
    elif data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16", errors="replace")
    else:
        best = charset_normalizer.from_bytes(data).best()
        text = str(best) if best else data.decode("latin-1")
    i = 0
    while True:
        m = _SKIP.match(text, i)
        if not m or m.end() == i:
            break
        i = m.end()
    return text[i:i + 64]


def _is_texty(path: Path) -> bool:
    best = charset_normalizer.from_path(path).best()
    if best is None or best.chaos > 0.5:
        return False
    text = str(best)
    if not text:
        return True
    ctrl = sum(1 for ch in text
               if unicodedata.category(ch) == "Cc" and ch not in "\n\r\t")
    return ctrl / len(text) < 0.01
