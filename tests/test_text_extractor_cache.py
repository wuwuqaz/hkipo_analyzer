from ipo_analyzer import text_extractor


def test_extract_pdf_text_cache_key_includes_max_pages(tmp_path, monkeypatch):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 sample")

    calls = {"count": 0}

    def fake_extract_impl(path, max_pages):
        calls["count"] += 1
        return f"pages={max_pages}"

    monkeypatch.setattr(text_extractor, "_extract_pdf_text_impl", fake_extract_impl)
    text_extractor.clear_text_cache()

    first = text_extractor.extract_pdf_text(str(pdf_path), max_pages=10)
    second = text_extractor.extract_pdf_text(str(pdf_path), max_pages=20)

    assert first == "pages=10"
    assert second == "pages=20"
    assert calls["count"] == 2
