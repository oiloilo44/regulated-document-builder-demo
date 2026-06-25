#!/usr/bin/env python3
"""데이터베이스 업데이트 기능을 제공하는 모듈"""

import os
from typing import Any

try:
    import pyodbc  # type: ignore[import]
except ImportError:  # pragma: no cover - 환경에 따라 pyodbc 부재 가능
    pyodbc = None  # type: ignore[assignment]

from .config import DBConnectionConfig
from .exceptions import PDFProcessingError
from .logger import setup_simple_logger


class DBUpdater:
    """데이터베이스 업데이트를 담당하는 클래스"""

    def __init__(self, db_config: DBConnectionConfig) -> None:
        """DB 업데이터 초기화
        
        Args:
            db_config: 데이터베이스 연결 설정
        """
        self.logger = setup_simple_logger(__name__)
        self.db_config = db_config
        self.logger.debug("[성공] DB 업데이터가 초기화되었습니다.")

    def _build_connection_string(self) -> str:
        """연결 문자열을 구성"""
        cfg = self.db_config
        base = (
            f"DRIVER={cfg.driver};"
            f"SERVER={cfg.server},{cfg.port};"
            f"DATABASE={cfg.database};"
        )
        if cfg.trusted_connection:
            return f"{base}Trusted_Connection=yes;"

        if not cfg.user or not cfg.password:
            raise PDFProcessingError(
                "DB 사용자 인증 정보가 누락되었습니다. 환경 변수를 확인하세요."
            )
        return f"{base}UID={cfg.user};PWD={cfg.password};"

    def _get_connection(self) -> Any:
        """DB 연결을 생성하고 반환"""
        if pyodbc is None:
            error_msg = (
                "pyodbc 모듈을 불러올 수 없습니다. ODBC 드라이버 및 의존성이 설치되었는지 확인하세요."
            )
            self.logger.error("[실패] %s", error_msg)
            raise PDFProcessingError(error_msg)

        try:
            self.logger.debug("[정보] 데이터베이스 연결을 시도합니다.")

            conn_str = self._build_connection_string()
            connection = pyodbc.connect(conn_str, autocommit=False)
            self.logger.debug("[성공] 데이터베이스 연결에 성공했습니다.")
            return connection
        except Exception as e:  # pyodbc.Error 포함
            error_msg = f"데이터베이스 연결 실패: {str(e)}"
            self.logger.error("[실패] %s", error_msg)
            raise PDFProcessingError(error_msg)

    def _build_update_statement(
        self,
        prt_req_no: str,
        prt_req_seq: str,
        output_filename: str,
        output_dir_path: str,
    ) -> tuple[str, tuple[Any, ...]]:
        """업데이트 쿼리와 파라미터를 생성"""
        
        query = """
            UPDATE ERPBiz.dbo.PPTestRecordDetail
            SET PrtFileName = ?,
                PrtFilePath = ?
            WHERE PrtReqNo = ? AND PrtReqSeq = ?
        """
        params = (
            output_filename,
            output_dir_path,
            prt_req_no,
            prt_req_seq,
        )
        return query, params


    def update_pdf_output_path(
        self,
        prt_req_no: str,
        prt_req_seq: str,
        input_pdf_path: str,
        output_filename: str,
        output_dir_path: str,
    ) -> bool:
        """
        PDF 출력 경로를 DB에 업데이트

        Args:
            prt_req_no: 대상 레코드 키 (PrtReqNo)
            prt_req_seq: 대상 일련번호 (PrtReqSeq)
            input_pdf_path: 입력 PDF 파일 경로
            output_filename: 출력 PDF 파일명
            output_dir_path: 출력 PDF 디렉토리 경로

        Returns:
            성공 여부
        """
        connection = None
        cursor = None
        try:
            # 파일명 추출 (로그용)
            input_filename = os.path.basename(input_pdf_path)

            self.logger.debug(
                "[시작] DB 업데이트 - 대상 키(PrtReqNo): %s, 일련번호(PrtReqSeq): %s, 입력파일: %s",
                prt_req_no,
                prt_req_seq,
                input_filename,
            )

            # DB 연결
            connection = self._get_connection()
            cursor = connection.cursor()

            update_sql, params = self._build_update_statement(
                prt_req_no,
                prt_req_seq,
                output_filename,
                output_dir_path,
            )
            cursor.execute(update_sql, params)


            # 업데이트된 행 수 확인
            rows_affected = cursor.rowcount
            connection.commit()

            if rows_affected > 0:
                self.logger.debug(
                    "[성공] DB 업데이트 완료 - 업데이트된 행: %d",
                    rows_affected,
                )
                return True
            else:
                self.logger.warning(
                    "[실패] DB 업데이트 실패 - 조건에 맞는 행을 찾을 수 없음 (PrtReqNo: %s, PrtReqSeq: %s)",
                    prt_req_no,
                    prt_req_seq,
                )
                self.logger.warning("쿼리: %s, 파라미터: %s", update_sql, params)
                return False

        except Exception as e:
            if pyodbc is not None and isinstance(e, pyodbc.Error):
                error_msg = f"DB 업데이트 실패: {str(e)}"
            else:
                error_msg = f"DB 업데이트 중 예상치 못한 오류 발생: {str(e)}"
            self.logger.error("[실패] %s", error_msg)
            if connection:
                connection.rollback()
            return False

        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if connection:
                connection.close()
                self.logger.debug("[정보] 데이터베이스 연결이 종료되었습니다.")

    def test_connection(self) -> bool:
        """
        DB 연결 테스트

        Returns:
            연결 성공 여부
        """
        connection = None
        try:
            self.logger.debug("[시작] 데이터베이스 연결 테스트를 시작합니다.")
            connection = self._get_connection()

            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()

            if result:
                self.logger.debug("[성공] 데이터베이스 연결 테스트에 성공했습니다.")
                return True
            else:
                self.logger.error(
                    "[실패] 데이터베이스 연결 테스트 실패: 응답이 없습니다."
                )
                return False

        except Exception as e:
            error_msg = f"데이터베이스 연결 테스트 실패: {str(e)}"
            self.logger.error("[실패] %s", error_msg)
            return False

        finally:
            if connection:
                connection.close()
