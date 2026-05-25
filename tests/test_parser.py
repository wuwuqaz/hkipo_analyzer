"""Parser 模块单元测试 — 覆盖 PDF 身份校验、基础信息提取。"""

from ipo_analyzer.parser import ProspectusParser
from ipo_analyzer.prospectus_basic_extractor import extract_prospectus_basic_info


class TestProspectusBasicExtractor:
    """招股书基础信息提取测试。"""

    def test_extract_offer_price(self):
        text = "Offer Price: HK$10.00 per Offer Share"
        info = {}
        extract_prospectus_basic_info(text, info)
        assert info.get("offer_price") == 10.0

    def test_extract_sector_fallback(self):
        """无明确 sector 信息时回退到 unknown。"""
        info = {}
        extract_prospectus_basic_info("some random text", info)
        assert info.get("sector") == "unknown"


class TestProspectusParser:
    """ProspectusParser 测试。"""

    def test_init_with_cache_dir(self, tmp_path):
        parser = ProspectusParser(cache_dir=str(tmp_path))
        assert parser.cache_dir == str(tmp_path)

    def test_invalid_pdf_rejected(self, tmp_path):
        """验证非 PDF 文件解析失败。"""
        parser = ProspectusParser(cache_dir=str(tmp_path))
        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_text("This is not a PDF file")

        result = parser.parse_pdf_file(str(fake_pdf), stock_code="09999", company_name="测试")
        assert result.get("parse_success") is False
        assert result.get("parse_error") is not None

    def test_parse_pdf_file_uses_cache_and_returns_defensive_copy(self, tmp_path, monkeypatch):
        parser = ProspectusParser(cache_dir=str(tmp_path))
        ProspectusParser._PARSE_CACHE.clear()
        pdf_path = tmp_path / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 sample")

        parse_calls = {"count": 0}

        def fake_extract_pdf_text(path):
            assert path == str(pdf_path)
            return "sample pdf text"

        def fake_validate_pdf_identity(text, stock_code=None, company_name=None):
            return {
                "name_match": True,
                "stock_code_match": True,
                "pdf_identity_confidence": "high",
            }

        def fake_extract_info(self, text):
            parse_calls["count"] += 1
            return {
                "parse_success": True,
                "score": 88,
                "nested": {"value": 1},
                "company_name": "Sample Co",
            }

        monkeypatch.setattr("ipo_analyzer.parser.extract_pdf_text", fake_extract_pdf_text)
        monkeypatch.setattr("ipo_analyzer.parser.validate_pdf_identity", fake_validate_pdf_identity)
        monkeypatch.setattr(ProspectusParser, "extract_info", fake_extract_info)

        first = parser.parse_pdf_file(str(pdf_path), stock_code="09999", company_name="Sample Co")
        first["nested"]["value"] = 999

        second = parser.parse_pdf_file(str(pdf_path), stock_code="09999", company_name="Sample Co")

        assert parse_calls["count"] == 1
        assert second["nested"]["value"] == 1
        assert second["score"] == 88
