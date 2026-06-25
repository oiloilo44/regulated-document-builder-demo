"""config.py 핵심 로직 단위 테스트"""

import json
import os
import tempfile
import pytest

from test_record_builder.config import (
    PositionConfig,
    TextConfig,
    DocumentBuilderConfig,
    DBConnectionConfig,
    SecureFileConfig,
)


class TestTextConfig:
    """TextConfig 기본값 및 속성 확인"""

    def test_default_values(self):
        cfg = TextConfig()
        assert cfg.font_size == 12
        assert cfg.font_name == "malgun"
        assert cfg.use_bold_font is False
        assert cfg.font_color == (0, 0, 0)
        assert cfg.align == "left"

    def test_custom_values(self):
        cfg = TextConfig(font_size=24, font_name="barcode", use_bold_font=True, font_color=(0, 0, 255))
        assert cfg.font_size == 24
        assert cfg.font_name == "barcode"
        assert cfg.use_bold_font is True
        assert cfg.font_color == (0, 0, 255)


class TestPositionConfig:
    """PositionConfig JSON 라운드트립 테스트"""

    def test_to_dict_returns_dict(self):
        pos = PositionConfig()
        result = pos.to_dict()
        assert isinstance(result, dict)
        assert "TestReqNo_rect" in result
        assert "TestReqNo_text" in result

    def test_from_dict_roundtrip(self):
        original = PositionConfig()
        data = original.to_dict()
        restored = PositionConfig.from_dict(data)

        assert restored.TestReqNo_rect == original.TestReqNo_rect
        assert restored.StockedAssetCode_rect == original.StockedAssetCode_rect
        assert restored.TestReqNo_text.font_size == original.TestReqNo_text.font_size
        assert restored.PrtReqNo_text.font_name == original.PrtReqNo_text.font_name

    def test_json_save_and_load(self, tmp_path):
        original = PositionConfig()
        json_path = str(tmp_path / "test_config.json")

        original.save_json(json_path)
        loaded = PositionConfig.load_json(json_path)

        assert loaded is not None
        assert loaded.TestReqNo_rect == original.TestReqNo_rect
        assert loaded.PrtReqNo_text.font_size == original.PrtReqNo_text.font_size

    def test_font_color_tuple_preserved(self):
        """JSON 직렬화 후 font_color가 list→tuple로 복원되는지 확인"""
        data = {
            "TestReqNo_rect": [10, 20, 30, 40],
            "TestReqNo_text": {
                "font_size": 10,
                "font_name": "malgun",
                "font_path": "assets/fonts/malgun.ttf",
                "font_bold_path": "assets/fonts/malgunbd.ttf",
                "use_bold_font": False,
                "font_color": [0, 0, 255],  # JSON에서는 list
                "align": "left",
            },
        }
        pos = PositionConfig.from_dict(data)
        assert isinstance(pos.TestReqNo_text.font_color, tuple)
        assert pos.TestReqNo_text.font_color == (0, 0, 255)

    def test_text_templates_default(self):
        """기본 text_templates가 올바르게 설정되는지 확인"""
        pos = PositionConfig()
        assert "TestReqNo" in pos.text_templates
        assert "{TestReqNo}" in pos.text_templates["TestReqNo"]
        assert "PrtReqNo" in pos.text_templates

    def test_text_templates_from_dict(self):
        """JSON에서 text_templates가 올바르게 로드되는지 확인"""
        data = {
            "text_templates": {
                "TestReqNo": "커스텀 관리번호: {TestReqNo}",
            }
        }
        pos = PositionConfig.from_dict(data)
        assert pos.text_templates["TestReqNo"] == "커스텀 관리번호: {TestReqNo}"

    def test_load_json_nonexistent_file(self):
        result = PositionConfig.load_json("/nonexistent/path.json")
        assert result is None


class TestDBConnectionConfig:
    """DBConnectionConfig 기본값 확인"""

    def test_default_port(self):
        cfg = DBConnectionConfig()
        assert cfg.port == int(os.getenv("DB_PORT", "1433"))

    def test_default_driver(self):
        cfg = DBConnectionConfig()
        assert "ODBC" in cfg.driver or cfg.driver == ""


class TestSecureFileConfig:
    """SecureFileConfig 필드 확인"""

    def test_temp_prefix_default(self):
        cfg = SecureFileConfig()
        assert cfg.temp_prefix == os.getenv("SECURE_FILE_TEMP_PREFIX", "temp_secure_file_")

    def test_max_wait_time(self):
        cfg = SecureFileConfig()
        assert cfg.max_wait_time > 0


class TestDocumentBuilderConfig:
    """통합 설정 구조 확인"""

    def test_all_sub_configs_present(self):
        cfg = DocumentBuilderConfig()
        assert hasattr(cfg, "positions")
        assert hasattr(cfg, "secure_file")
        assert hasattr(cfg, "ssh")
        assert hasattr(cfg, "storage")
        assert hasattr(cfg, "db")
        assert hasattr(cfg, "resources")

    def test_db_config_is_dbconnectionconfig(self):
        cfg = DocumentBuilderConfig()
        assert isinstance(cfg.db, DBConnectionConfig)
