# tests/test_perf.py — перф-смоук §17: мягкий порог, warning вместо fail
import time
import warnings

import pymupdf
import pytest

from librarian.config import load_config
from librarian.pipeline import run_ingest

_PARA = ("The keeper wrote down every light he saw across the strait during "
         "the long night watch while the sea kept counting the hours. ") * 4


@pytest.mark.perf
def test_pdf_500_pages_under_30s(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    # мерим ПРОДОВЫЙ путь: у пользователя env-обхода нет, extract_timeout_s=120 →
    # spawn-guard + pickle RawDoc через Pipe входят в бюджет 30 с (§6.0/§17)
    monkeypatch.delenv("LIB_EXTRACT_INPROCESS", raising=False)
    pdf = tmp_path / "big.pdf"
    doc = pymupdf.open()
    for i in range(500):
        page = doc.new_page(width=595, height=842)
        if i % 10 == 0:
            page.insert_text((72, 90), f"Chapter {i // 10 + 1}",
                             fontsize=16, fontname="helv")
        page.insert_textbox(pymupdf.Rect(72, 120, 520, 780), _PARA * 4,
                            fontsize=10, fontname="helv")
    doc.save(pdf, deflate=True)
    doc.close()
    t0 = time.monotonic()
    outcome = run_ingest([pdf], load_config(None), tmp_path / "lib")[0]
    dt = time.monotonic() - t0
    assert outcome.status in ("ok", "review")
    if dt > 30:
        warnings.warn(f"перф-смоук: 500-страничный PDF за {dt:.1f} с (порог 30 с)")


def test_network_is_blocked():
    import socket
    import pytest_socket
    with pytest.raises(pytest_socket.SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("127.0.0.1", 9))
