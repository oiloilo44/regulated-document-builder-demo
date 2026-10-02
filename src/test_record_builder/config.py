#!/usr/bin/env python3
"""시험 기록서 문서 빌더 설정"""

import os
import json
import dataclasses
import logging
from typing import Tuple, Optional, Any, Dict
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv(override=True)
logger = logging.getLogger(__name__)

# -----------------
# Fonts & Settings
# -----------------
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _get_asset_path(rel_path: str) -> str:
    # 현재 디렉토리에 있으면 그것을 우선 사용, 없으면 BASE_DIR 기준 사용
    if os.path.exists(rel_path):
        return os.path.abspath(rel_path)
    return os.path.join(_BASE_DIR, rel_path)

ASSET_FONT_MALGUN = os.getenv("ASSET_FONT_MALGUN", "malgun.ttf")
ASSET_FONT_MALGUN_BOLD = os.getenv("ASSET_FONT_MALGUN_BOLD", "malgunbd.ttf")
ASSET_FONT_BARCODE = os.getenv("ASSET_FONT_BARCODE", _get_asset_path("assets/fonts/CODE39-3.TTF"))

@dataclass
class TextConfig:
    """텍스트/바코드 속상 공통 클래스"""
    
    font_size: int = 12
    font_name: str = "malgun"
    font_path: str = ASSET_FONT_MALGUN
    font_bold_path: str = ASSET_FONT_MALGUN_BOLD
    use_bold_font: bool = False
    font_color: Tuple[int, int, int] = (0, 0, 0)
    
    # Text alignments
    align: str = "left"  # left, center, right

@dataclass
class PositionConfig:
    """위치 및 기본 텍스트 렌더링 설정
    좌표는 (x0, y0, x1, y1) 형식으로 박스 영역을 지정할 수 있으며, 
    x0, y0는 PyMuPDF의 좌표계 (Point 단위)에 해당함.
    """
    
    # 템플릿(기준) 문서의 특정 rect 범위 내에 텍스트를 배치
    # 사용자가 인자로 넘기는 9가지 데이터에 대한 위치 설정
    
    # 1. 관리번호
    TestReqNo_rect: Tuple[float, float, float, float] = (150, 4, 300, 24)
    TestReqNo_text: TextConfig = field(default_factory=lambda: TextConfig(font_size=10, use_bold_font=False))

    # 2. 제조/입고번호
    StockedAssetCode_rect: Tuple[float, float, float, float] = (350, 4, 550, 24)
    StockedAssetCode_text: TextConfig = field(default_factory=lambda: TextConfig(font_size=10, use_bold_font=False))
    
    # 3. 요청자
    PrtReqEmpName_rect: Tuple[float, float, float, float] = (70, 4, 200, 24)
    PrtReqEmpName_text: TextConfig = field(default_factory=lambda: TextConfig(font_size=10, use_bold_font=False))

    # 4. 승인자
    ConfirmEmpName_rect: Tuple[float, float, float, float] = (220, 4, 350, 24)
    ConfirmEmpName_text: TextConfig = field(default_factory=lambda: TextConfig(font_size=10, use_bold_font=False))
    
    # 5. 용도
    TestUseKind_rect: Tuple[float, float, float, float] = (400, 4, 550, 24)
    TestUseKind_text: TextConfig = field(default_factory=lambda: TextConfig(font_size=10, use_bold_font=False))
    
    # 6. 승인일자
    ApprovalDate_rect: Tuple[float, float, float, float] = (150, 810, 300, 830)
    ApprovalDate_text: TextConfig = field(default_factory=lambda: TextConfig(font_size=10, use_bold_font=False))
    
    # 7. 출력횟수
    RePrtCnt_rect: Tuple[float, float, float, float] = (350, 810, 550, 830)
    RePrtCnt_text: TextConfig = field(default_factory=lambda: TextConfig(font_size=10, use_bold_font=False))
    
    # 8. 복사방지 이미지 (워터마크용 배경 전면 혹은 지정위치 삽입 여부, 기본값: 페이지 하단이나 배경 전체 - 추후 로직 확인)
    watermark_image_rect: Tuple[float, float, float, float] = (0, 0, 595, 842) # A4 Full
    watermark_opacity: float = 0.7  # 워터마크 이미지 투명도 (0.0 ~ 1.0)
    
    # 9. 관리번호2 (바코드)
    PrtReqNo_rect: Tuple[float, float, float, float] = (100, 30, 550, 100)
    PrtReqNo_text: TextConfig = field(default_factory=lambda: TextConfig(
        font_size=24, 
        font_name="barcode", 
        font_path=ASSET_FONT_BARCODE, 
        align="center"
    ))

    # 텍스트 포맷 템플릿 (layout_config.json에서 관리)
    text_templates: Dict[str, str] = field(default_factory=lambda: {
        "TestReqNo": "■ 관리번호 ({TestReqNo})",
        "StockedAssetCode": "■ 제조번호/입고번호 ({StockedAssetCode})",
        "PrtReqEmpName": "■ 요청자 ({PrtReqEmpName}) / 승인자 ({ConfirmEmpName})",
        "TestUseKind": "■ 용도 ({TestUseKind})",
        "ConfirmEmpName": "■ 출력페이지 {page}/{total_pages}",
        "ApprovalDate": "■ 승인일자 {ApprovalDate}",
        "RePrtCnt": "■ 출력횟수 ({RePrtCnt}회){reason}",
        "PrtReqNo": "*{PrtReqNo}{PrtReqSeq}*",
    })
    def to_dict(self) -> Dict[str, Any]:
        """dataclass 객체를 dict로 변환 (JSON 저장용)"""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PositionConfig":
        """dict 데이터로부터 PositionConfig 객체 생성 (JSON 로드용)"""
        kwargs: Dict[str, Any] = {}
        for f in dataclasses.fields(cls):
            if f.name in data:
                val = data[f.name]
                if f.name == "text_templates" and isinstance(val, dict):
                    kwargs[f.name] = val
                elif f.name.endswith("_text") and isinstance(val, dict):
                    # TextConfig 복원
                    text_kwargs = dict(val)
                    if "font_color" in text_kwargs and isinstance(text_kwargs["font_color"], list):
                        text_kwargs["font_color"] = tuple(text_kwargs["font_color"])
                    kwargs[f.name] = TextConfig(**text_kwargs)
                elif f.name.endswith("_rect") and isinstance(val, list):
                    # Tuple[float,float,float,float] 복원
                    kwargs[f.name] = tuple(val)
                else:
                    kwargs[f.name] = val
        return cls(**kwargs)

    def save_json(self, file_path: str) -> None:
        """설정을 JSON 파일로 저장"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.warning("Error saving config to JSON: %s", e)

    @classmethod
    def load_json(cls, file_path: str) -> Optional["PositionConfig"]:
        """JSON 파일에서 설정 불러오기"""
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.warning("Error loading config from JSON: %s", e)
            return None

@dataclass
class LoggingConfig:
    """로깅 설정"""
    level: str = os.getenv("LOG_LEVEL", "INFO")
    file_path: str = os.getenv("LOG_FILE_PATH", "logs/test_record_builder.log")
    max_file_size: int = int(os.getenv("LOG_MAX_FILE_SIZE", "10485760"))  # 10MB
    backup_count: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    format: str = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")

@dataclass
class SSHConfig:
    """SSH 연결 설정"""
    hostname: str = os.getenv("SSH_HOSTNAME", "")
    port: int = int(os.getenv("SSH_PORT", "22"))
    username: str = os.getenv("SSH_USERNAME", "")
    password: str = os.getenv("SSH_PASSWORD", "")
    private_key_path: Optional[str] = os.getenv("SSH_PRIVATE_KEY_PATH")
    connection_timeout: int = int(os.getenv("SSH_CONNECTION_TIMEOUT", "30"))

@dataclass
class SecureFileConfig:
    """secure file preprocessing 관련 설정"""
    input_path: str = os.getenv("SECURE_FILE_INPUT_PATH", "work/encrypted")
    output_path: str = os.getenv("SECURE_FILE_OUTPUT_PATH", "work/decrypted")
    polling_interval: int = int(os.getenv("SECURE_FILE_POLLING_INTERVAL", "5"))
    max_wait_time: int = int(os.getenv("SECURE_FILE_MAX_WAIT_TIME", "300"))
    file_extension: str = os.getenv("SECURE_FILE_EXTENSION", ".pdf")
    file_stability_time: int = int(os.getenv("SECURE_FILE_STABILITY_TIME", "5"))
    max_stability_wait: int = int(os.getenv("SECURE_FILE_MAX_STABILITY_WAIT", "30"))
    max_download_retries: int = int(os.getenv("SECURE_FILE_MAX_DOWNLOAD_RETRIES", "5"))
    download_retry_delay: int = int(os.getenv("SECURE_FILE_DOWNLOAD_RETRY_DELAY", "3"))
    temp_prefix: str = os.getenv("SECURE_FILE_TEMP_PREFIX", "temp_secure_file_")

@dataclass
class StorageConfig:
    """storage 관련 설정"""
    completed_path: str = os.getenv("STORAGE_COMPLETED_PATH", "output/completed")

@dataclass
class ResourceConfig:
    """보조 리소스 설정"""
    watermark_image_path: str = os.getenv("WATERMARK_IMAGE_PATH", _get_asset_path("assets/images/controlled_copy.jpg"))

@dataclass
class DBConnectionConfig:
    """데이터베이스 연결 설정"""
    server: str = os.getenv("DB_SERVER", "")
    port: int = int(os.getenv("DB_PORT", "1433"))
    database: str = os.getenv("DB_NAME", "")
    user: str = os.getenv("DB_USER", "")
    password: str = os.getenv("DB_PASSWORD", "")
    driver: str = os.getenv("DB_DRIVER", "{ODBC Driver 17 for SQL Server}")
    trusted_connection: bool = os.getenv("DB_TRUSTED_CONNECTION", "false").lower() == "true"

@dataclass
class DocumentBuilderConfig:
    """전체 설정 통합"""
    positions: PositionConfig = field(default_factory=PositionConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    secure_file: SecureFileConfig = field(default_factory=SecureFileConfig)
    ssh: SSHConfig = field(default_factory=SSHConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    db: DBConnectionConfig = field(default_factory=DBConnectionConfig)
