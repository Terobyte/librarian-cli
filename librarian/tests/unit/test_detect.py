import zipfile
import pytest
from librarian.detect import detect
from librarian.errors import BrokenFileError, DetectError
from librarian.ir import Format

def _zip(tmp_path, name, entries):
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        for arcname, data in entries:
            z.writestr(arcname, data)
    return p

def test_pdf(tmp_path):
    p = tmp_path / "x.bin"; p.write_bytes(b"%PDF-1.7 rest")
    assert detect(p) is Format.PDF

def test_epub(tmp_path):
    p = _zip(tmp_path, "b.epub", [("mimetype", "application/epub+zip"), ("x.xhtml", "<html/>")])
    assert detect(p) is Format.EPUB

def test_docx(tmp_path):
    p = _zip(tmp_path, "d.docx", [("word/document.xml", "<w:document/>")])
    assert detect(p) is Format.DOCX

def test_fb2_zip(tmp_path):
    p = _zip(tmp_path, "b.fb2.zip", [("book.fb2", "<FictionBook/>"), ("cover.jpg", "xx")])
    assert detect(p) is Format.FB2

def test_fb2_zip_two_fb2_is_error(tmp_path):
    p = _zip(tmp_path, "b.zip", [("a.fb2", "x"), ("b.fb2", "y")])
    with pytest.raises(DetectError):
        detect(p)

def test_zip_other_is_error(tmp_path):
    with pytest.raises(DetectError):
        detect(_zip(tmp_path, "z.zip", [("data.txt", "hi")]))

def test_fb2_xml_with_comment_and_decl(tmp_path):
    p = tmp_path / "b.fb2"
    p.write_text('<?xml version="1.0"?>\n<!-- к -->\n<FictionBook xmlns="...">', encoding="utf-8")
    assert detect(p) is Format.FB2

def test_html_xhtml(tmp_path):
    p = tmp_path / "a.html"
    p.write_text("﻿  <!-- x --><!DOCTYPE HTML><html>", encoding="utf-8")
    assert detect(p) is Format.HTML

def test_md_by_extension(tmp_path):
    p = tmp_path / "note.md"; p.write_text("# Hi", encoding="utf-8")
    assert detect(p) is Format.MD

def test_txt_cp1251(tmp_path):
    p = tmp_path / "т.txt"; p.write_bytes("Глава первая. Проза.".encode("cp1251"))
    assert detect(p) is Format.TXT

def test_binary_is_detect_error(tmp_path):
    p = tmp_path / "x.dat"; p.write_bytes(bytes(range(256)) * 8)
    with pytest.raises(DetectError):
        detect(p)

def test_broken_zip(tmp_path):
    p = tmp_path / "x.epub"; p.write_bytes(b"PK\x03\x04" + b"\x00" * 30)
    with pytest.raises(BrokenFileError):
        detect(p)


def test_detect_no_fd_leak(tmp_path, monkeypatch):
    from pathlib import Path
    p = tmp_path / "test.txt"
    p.write_text("Some text content to detect as plain txt", encoding="utf-8")
    
    opened_files = []
    original_open = Path.open
    
    def mock_open(self, *args, **kwargs):
        f = original_open(self, *args, **kwargs)
        opened_files.append(f)
        return f
        
    monkeypatch.setattr(Path, "open", mock_open)
    
    detect(p)
    
    assert len(opened_files) > 0
    for f in opened_files:
        assert f.closed, f"File {f} was not closed!"

