"""document_builder.py 핵심 로직 단위 테스트"""

import pytest

from test_record_builder.document_builder import TestRecordBuilder
from test_record_builder.config import DocumentBuilderConfig, TextConfig


class TestNormalizeColor:
    """_normalize_color 정적 메서드 테스트"""

    def test_black(self):
        assert TestRecordBuilder._normalize_color((0, 0, 0)) == (0.0, 0.0, 0.0)

    def test_white(self):
        assert TestRecordBuilder._normalize_color((255, 255, 255)) == (1.0, 1.0, 1.0)

    def test_blue(self):
        r, g, b = TestRecordBuilder._normalize_color((0, 0, 255))
        assert r == 0.0
        assert g == 0.0
        assert abs(b - 1.0) < 1e-9

    def test_arbitrary_color(self):
        r, g, b = TestRecordBuilder._normalize_color((128, 64, 32))
        assert abs(r - 128 / 255) < 1e-9
        assert abs(g - 64 / 255) < 1e-9
        assert abs(b - 32 / 255) < 1e-9


class TestBuilderInit:
    """TestRecordBuilder 초기화 테스트"""

    def test_init_no_doc(self):
        config = DocumentBuilderConfig()
        builder = TestRecordBuilder(config)
        assert builder.doc is None

    def test_close_pdf_when_none(self):
        """문서가 없을 때 close_pdf 호출 시 에러 없이 통과"""
        config = DocumentBuilderConfig()
        builder = TestRecordBuilder(config)
        builder.close_pdf()  # should not raise
        assert builder.doc is None

    def test_save_pdf_raises_without_doc(self):
        """문서가 없을 때 save_pdf 호출 시 RuntimeError 발생"""
        config = DocumentBuilderConfig()
        builder = TestRecordBuilder(config)
        with pytest.raises(RuntimeError, match="열려있는 PDF 문서가 없습니다"):
            builder.save_pdf("output.pdf")

    def test_process_document_raises_without_doc(self):
        """문서가 없을 때 process_document 호출 시 RuntimeError 발생"""
        config = DocumentBuilderConfig()
        builder = TestRecordBuilder(config)
        with pytest.raises(RuntimeError, match="PDF 문서가 열려있지 않습니다"):
            builder.process_document({}, "watermark.jpg")
