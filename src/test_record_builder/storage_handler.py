#!/usr/bin/env python3
"""storage 파일 검색 및 송수신 모듈"""

import os
import re
import shutil
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime

from test_record_builder.config import StorageConfig
from test_record_builder.logger import setup_simple_logger
from test_record_builder.exceptions import DocumentBuilderError

class StorageHandlerError(DocumentBuilderError):
    """storage 처리 관련 예외"""
    pass

class StorageHandler:
    def __init__(self, config: StorageConfig):
        self.config = config
        self.logger = setup_simple_logger(__name__)
        self.logger.debug("[성공] storage 핸들러가 초기화되었습니다.")

    def copy_to_local(self, remote_path: str, local_dir: str) -> str:
        """storage 파일을 로컬 워킹 디렉토리로 복사"""
        os.makedirs(local_dir, exist_ok=True)
        filename = os.path.basename(remote_path)
        local_path = os.path.join(local_dir, filename)
        
        self.logger.debug("[시작] 로컬 복사: %s -> %s", remote_path, local_path)
        try:
            shutil.copy2(remote_path, local_path)
            self.logger.debug("[성공] 복사 완료")
            return local_path
        except Exception as e:
            self.logger.error("[실패] 파일 복사 중 오류: %s", str(e))
            raise StorageHandlerError(f"storage -> 로컬 복사 실패: {str(e)}")
            
    def copy_to_storage(self, local_path: str, custom_filename: Optional[str] = None) -> str:
        """결과물 로컬 파일을 storage 완료 폴더로 복사"""
        storage_completed_dir = Path(self.config.completed_path)
        
        try:
            storage_completed_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.warning("완료 폴더 생성 실패 (이미 존재하거나 권한 부족): %s", str(e))
            
        filename = custom_filename or os.path.basename(local_path)
        dest_path = storage_completed_dir / filename
        
        self.logger.debug("[시작] storage 업로드: %s -> %s", local_path, dest_path)
        try:
            shutil.copy2(local_path, dest_path)
            self.logger.debug("[성공] storage 업로드 완료")
            return str(dest_path)
        except Exception as e:
            self.logger.error("[실패] storage 업로드 중 오류: %s", str(e))
            raise StorageHandlerError(f"로컬 -> storage 업로드 실패: {str(e)}")
