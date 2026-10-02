"""외부 서비스와 전용 폰트 없이 실행하는 공개 데모 회귀 테스트."""
import json
from pathlib import Path

import fitz

from test_record_builder.config import DocumentBuilderConfig, TextConfig
from test_record_builder.document_builder import TestRecordBuilder as Builder
from test_record_builder.main import _load_layout_config, main

ROOT = Path(__file__).resolve().parents[1]


def test_missing_font_preserves_korean():
    builder = Builder(DocumentBuilderConfig())
    with fitz.open() as document:
        page = document.new_page()
        builder._insert_text(
            page, "요청자 승인자", (20, 20, 400, 70),
            TextConfig(font_path="/missing/demo-font.ttf"),
        )
        assert "요청자 승인자" in page.get_text()


def test_environment_fonts_override_layout(monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("ASSET_FONT_MALGUN", "/custom/regular.ttf")
    monkeypatch.setenv("ASSET_FONT_MALGUN_BOLD", "/custom/bold.ttf")
    monkeypatch.setenv("ASSET_FONT_BARCODE", "/custom/barcode.ttf")
    config = DocumentBuilderConfig()
    _load_layout_config(config)
    assert config.positions.TestReqNo_text.font_path == "/custom/regular.ttf"
    assert config.positions.TestReqNo_text.font_bold_path == "/custom/bold.ttf"
    assert config.positions.PrtReqNo_text.font_path == "/custom/barcode.ttf"


def test_json_pipeline_outputs_requested_page(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DB_UPDATE_ENABLED", "false")
    monkeypatch.setenv("SECURE_FILE_ENABLED", "false")
    (tmp_path / "layout_config.json").write_text((ROOT / "layout_config.json").read_text())
    source = tmp_path / "input.pdf"
    with fitz.open() as document:
        for number in (1, 2):
            page = document.new_page()
            page.insert_text((60, 120), f"Synthetic page {number}")
        document.save(source)
    job = json.loads((ROOT / "samples/jobs.json").read_text())[0]
    job.update(InputPdfPath=str(source), PageReqALLYn="N", PageReqStartNo="2", PageReqEndNo="2")
    jobs = tmp_path / "jobs.json"
    jobs.write_text(json.dumps([job]))
    assert main(["--json", str(jobs)]) == 0
    outputs = list((tmp_path / "output/completed").glob("*.pdf"))
    assert len(outputs) == 1
    with fitz.open(outputs[0]) as document:
        assert len(document) == 1
        text = document[0].get_text()
        assert "Synthetic page 2" in text
        assert "REQ-001" in text
        assert "요청자" in text
        assert "2026-01-01" in text
        assert "barcode" in " ".join(str(font) for font in document[0].get_fonts()).lower()
        assert document[0].get_images()


def test_save_to_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    builder = Builder(DocumentBuilderConfig())
    builder.doc = fitz.open()
    builder.doc.new_page()
    try:
        builder.save_pdf("result.pdf")
        assert (tmp_path / "result.pdf").is_file()
    finally:
        builder.close_pdf()
