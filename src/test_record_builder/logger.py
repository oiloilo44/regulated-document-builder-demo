#!/usr/bin/env python3
"""로깅 설정 모듈

NOTE: 이 모듈은 config.py에 의존하지 않습니다 (순환 의존 방지).
      환경변수에서 직접 로깅 설정을 읽습니다.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경변수에서 로깅 설정 직접 읽기 (config.py 의존 제거)
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
_LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "logs/test_record_builder.log")
_LOG_MAX_FILE_SIZE = int(os.getenv("LOG_MAX_FILE_SIZE", "10485760"))  # 10MB
_LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
_DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_DEFAULT_SIMPLE_FORMAT = "%(asctime)s - %(message)s"
_LOG_FORMAT = os.getenv("LOG_FORMAT", _DEFAULT_LOG_FORMAT)
_LOG_SIMPLE_FORMAT = os.getenv("LOG_SIMPLE_FORMAT", _DEFAULT_SIMPLE_FORMAT)


def _coerce_log_format(value: str, fallback: str) -> str:
    try:
        logging.Formatter(value)
        return value
    except ValueError:
        return fallback

def get_log_level(level_str: str) -> int:
    """문자열 로그 레벨을 logging 상수로 변환합니다."""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_str.upper(), logging.INFO)


def setup_logger(
    name: str = "manu_pack_doc_builder",
    level: Optional[int] = None,
    log_file: Optional[str] = None,
    use_simple_format: bool = True,
) -> logging.Logger:
    """
    프로젝트용 로거를 설정합니다.

    Args:
        name: 로거 이름
        level: 로그 레벨 (None이면 환경변수에서 읽기)
        log_file: 로그 파일 경로 (None이면 환경변수에서 읽기)
        use_simple_format: 간단한 포맷 사용 여부

    Returns:
        설정된 로거 객체
    """
    logger = logging.getLogger(name)

    # 이미 핸들러가 설정되어 있으면 반환
    if logger.handlers:
        return logger

    # 환경변수에서 설정값 읽기
    if level is None:
        level = get_log_level(_LOG_LEVEL)

    if log_file is None:
        log_file = _LOG_FILE_PATH

    # 로그 포맷 설정
    if use_simple_format:
        console_format = _LOG_SIMPLE_FORMAT
        file_format = _LOG_FORMAT
    else:
        console_format = file_format = _LOG_FORMAT

    
    console_format = _coerce_log_format(console_format, _DEFAULT_SIMPLE_FORMAT)
    file_format = _coerce_log_format(file_format, _DEFAULT_LOG_FORMAT)
# 로거 자체는 모든 로그(DEBUG)를 통과시키도록 가장 낮은 레벨로 개방합니다.
    # 그래야 파일 핸들러가 DEBUG 로그를 잡을 수 있습니다.
    logger.setLevel(logging.DEBUG)

    # 콘솔 핸들러 (간단한 포맷)
    console_formatter = logging.Formatter(
        console_format, datefmt="%H:%M:%S"  # 콘솔은 시간만 표시
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러 (상세한 포맷)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_formatter = logging.Formatter(file_format, datefmt="%Y-%m-%d %H:%M:%S")

        if _LOG_MAX_FILE_SIZE > 0 and _LOG_BACKUP_COUNT > 0:
            # 설정된 최대 크기를 초과하면 자동으로 로그 파일을 회전
            file_handler: logging.Handler = RotatingFileHandler(
                log_path,
                maxBytes=_LOG_MAX_FILE_SIZE,
                backupCount=_LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
        else:
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
        
        # 파일 핸들러에는 입력된 level과 상관없이 항상 파일에 모든 로그를 기록합니다.
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def setup_simple_logger(name: str = "manu_pack_doc_builder") -> logging.Logger:
    """간단한 로그만 출력하는 로거를 설정합니다."""
    return setup_logger(name=name, use_simple_format=True)


def setup_verbose_logger(
    name: str = "manu_pack_doc_builder", log_file: Optional[str] = None
) -> logging.Logger:
    """상세한 로그를 출력하는 로거를 설정합니다."""
    return setup_logger(
        name=name, level=logging.DEBUG, log_file=log_file, use_simple_format=False
    )
