#!/usr/bin/env python3
"""SSH 연결 및 파일 전송을 처리하는 모듈"""

from __future__ import annotations
import time
from pathlib import Path
from typing import Optional, Any

import paramiko  # type: ignore[import-untyped]
from paramiko import SSHClient, SFTPClient

from .config import SSHConfig, SecureFileConfig
from .exceptions import DocumentBuilderError
from .logger import setup_simple_logger


class SSHConnectionError(DocumentBuilderError):
    """SSH 연결 오류"""

    pass


class FileTransferError(DocumentBuilderError):
    """파일 전송 오류"""

    pass


class SSHHandler:
    """SSH 연결 및 파일 전송을 처리하는 클래스"""

    def __init__(self, ssh_config: SSHConfig, secure_file_config: SecureFileConfig) -> None:
        """
        SSH 핸들러 초기화

        Args:
            ssh_config: SSH 연결 설정
            secure_file_config: secure file preprocessing 설정
        """
        self.ssh_config = ssh_config
        self.secure_file_config = secure_file_config
        self.ssh_client: Optional[SSHClient] = None
        self.sftp_client: Optional[SFTPClient] = None
        self.logger = setup_simple_logger(__name__)

    # ========== Context Manager Methods ==========

    def __enter__(self) -> SSHHandler:
        """컨텍스트 매니저 진입"""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """컨텍스트 매니저 종료"""
        self.disconnect()

    # ========== Connection Management ==========

    def connect(self) -> None:
        """SSH 서버에 연결"""
        try:
            self.logger.debug(
                "[시작] SSH 연결 시도: %s:%s",
                self.ssh_config.hostname,
                self.ssh_config.port,
            )

            self.ssh_client = SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507

            # 연결 시도
            self.ssh_client.connect(
                hostname=self.ssh_config.hostname,
                port=self.ssh_config.port,
                username=self.ssh_config.username,
                password=self.ssh_config.password,
                key_filename=self.ssh_config.private_key_path,
                timeout=self.ssh_config.connection_timeout,
            )
            self.sftp_client = self.ssh_client.open_sftp()

            self.logger.debug("[성공] SSH 연결 성공")

        except Exception as e:
            self.logger.error("[실패] SSH 연결 실패: %s", str(e))
            raise SSHConnectionError(f"SSH 연결 실패: {str(e)}")

    def disconnect(self) -> None:
        """SSH 연결 해제"""
        try:
            if self.sftp_client:
                self.sftp_client.close()
                self.sftp_client = None

            if self.ssh_client:
                self.ssh_client.close()
                self.ssh_client = None

            self.logger.debug("[정보] SSH 연결이 해제되었습니다.")

        except Exception as e:
            self.logger.warning("[경고] SSH 연결 해제 중 오류 발생: %s", str(e))

    # ========== File Transfer Methods ==========

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """
        파일을 원격 서버에 업로드

        Args:
            local_path: 로컬 파일 경로
            remote_path: 원격 파일 경로
        """
        if not self.sftp_client:
            raise SSHConnectionError("SSH 연결이 설정되지 않았습니다")

        try:
            self.logger.debug("[시작] 파일 업로드: %s -> %s", local_path, remote_path)

            # 로컬 파일 존재 확인
            if not Path(local_path).exists():
                raise FileTransferError(f"로컬 파일을 찾을 수 없습니다: {local_path}")

            # 원격 디렉토리 생성 (존재하지 않는 경우)
            remote_dir = str(Path(remote_path).parent)
            self._ensure_remote_directory(remote_dir)

            # 파일 업로드
            self.sftp_client.put(local_path, remote_path)

            self.logger.debug("[성공] 파일 업로드 완료: %s", remote_path)

        except FileTransferError:
            raise
        except Exception as e:
            self.logger.error("[실패] 파일 업로드 실패: %s", str(e))
            raise FileTransferError(f"파일 업로드 실패: {str(e)}")

    def download_file(
        self,
        remote_path: str,
        local_path: str,
        max_retries: int = 3,
        retry_delay: int = 2,
    ) -> None:
        """
        원격 서버에서 파일을 다운로드 (재시도 로직 포함)

        Args:
            remote_path: 원격 파일 경로
            local_path: 로컬 파일 경로
            max_retries: 최대 재시도 횟수
            retry_delay: 재시도 간격 (초)
        """
        if not self.sftp_client:
            raise SSHConnectionError("SSH 연결이 설정되지 않았습니다")

        last_exception = None

        for attempt in range(max_retries):
            try:
                self.logger.debug(
                    "[시작] 파일 다운로드 시도 %d/%d: %s -> %s",
                    attempt + 1,
                    max_retries,
                    remote_path,
                    local_path,
                )

                # 원격 파일 존재 확인
                if not self._remote_file_exists(remote_path):
                    raise FileTransferError(
                        f"원격 파일을 찾을 수 없습니다: {remote_path}"
                    )

                # 파일 완전성 확인 (파일이 완전히 이동되었는지 확인)
                if not self._wait_for_file_completion(
                    remote_path,
                    stability_time=self.secure_file_config.file_stability_time,
                    max_wait=self.secure_file_config.max_stability_wait,
                ):
                    raise FileTransferError(
                        f"파일이 완전히 준비되지 않았습니다: {remote_path}"
                    )

                # 로컬 디렉토리 생성 (존재하지 않는 경우)
                local_dir = Path(local_path).parent
                local_dir.mkdir(parents=True, exist_ok=True)

                # 파일 다운로드
                self.sftp_client.get(remote_path, local_path)

                # 다운로드 완료 후 파일 크기 확인
                if self._verify_download_integrity(remote_path, local_path):
                    self.logger.debug("[성공] 파일 다운로드 완료: %s", local_path)
                    return
                else:
                    raise FileTransferError("다운로드된 파일 크기가 일치하지 않습니다")

            except Exception as e:
                last_exception = e
                self.logger.warning(
                    "[경고] 파일 다운로드 시도 %d 실패: %s", attempt + 1, str(e)
                )

                # 마지막 시도가 아니면 잠시 대기
                if attempt < max_retries - 1:
                    self.logger.debug("[정보] %d초 대기 후 재시도합니다...", retry_delay)
                    time.sleep(retry_delay)

        # 모든 재시도 실패
        error_detail = str(last_exception) if last_exception else "알 수 없는 오류"
        self.logger.error("[실패] 파일 다운로드 최종 실패: %s", error_detail)
        raise FileTransferError(f"파일 다운로드 실패: {error_detail}")

    # ========== File Operations ==========

    def file_exists(self, remote_path: str) -> bool:
        """
        원격 파일 존재 여부 확인

        Args:
            remote_path: 원격 파일 경로

        Returns:
            파일 존재 여부
        """
        return self._remote_file_exists(remote_path)

    # ========== Command Execution ==========

    def execute_command(self, command: str) -> tuple[str, str, int]:
        """
        원격 서버에서 명령어 실행

        Args:
            command: 실행할 명령어

        Returns:
            (stdout, stderr, exit_code) 튜플
        """
        if not self.ssh_client:
            raise SSHConnectionError("SSH 연결이 설정되지 않았습니다")

        try:
            self.logger.debug("[정보] 명령어 실행: %s", command)

            stdin, stdout, stderr = self.ssh_client.exec_command(command)  # nosec B601

            # 다양한 인코딩을 시도하여 디코딩
            stdout_data = self._decode_output(stdout.read())
            stderr_data = self._decode_output(stderr.read())
            exit_code = stdout.channel.recv_exit_status()

            self.logger.debug("[성공] 명령어 실행 완료: exit_code=%d", exit_code)

            return stdout_data, stderr_data, exit_code

        except Exception as e:
            self.logger.error("[실패] 명령어 실행 실패: %s", str(e))
            raise SSHConnectionError(f"명령어 실행 실패: {str(e)}")

    # ========== Private Helper Methods ==========

    def _ensure_remote_directory(self, remote_path: str) -> None:
        """원격 디렉토리 생성 (존재하지 않는 경우)"""
        if not self.sftp_client:
            return
        normalized = remote_path.strip()
        if not normalized or normalized == ".":
            return
        is_absolute = normalized.startswith("/")
        try:
            self.sftp_client.stat(normalized)
            return
        except FileNotFoundError:
            pass

        try:
            self.logger.debug("[정보] 원격 디렉토리를 생성합니다: %s", normalized)
            self.sftp_client.mkdir(normalized)
            return
        except FileNotFoundError:
            # 부모 디렉토리가 없을 수 있어 재귀적으로 생성 시도
            pass
        except Exception as exc:
            # 다른 예외는 부모 생성 재시도로 처리
            self.logger.debug(
                "[정보] 원격 디렉토리 생성 재시도 필요(%s): %s", normalized, str(exc)
            )

        parts = [part for part in normalized.split("/") if part]
        current = "/" if is_absolute else ""
        for part in parts:
            if current in ("", "/"):
                current = f"/{part}" if is_absolute else part
            else:
                current = f"{current}/{part}"
            try:
                self.sftp_client.stat(current)
                continue
            except FileNotFoundError:
                self.logger.debug("[정보] 원격 디렉토리를 생성합니다: %s", current)
                try:
                    self.sftp_client.mkdir(current)
                except Exception as exc:
                    # 다른 프로세스가 먼저 생성한 경우 등을 다시 확인
                    try:
                        self.sftp_client.stat(current)
                    except Exception:
                        raise FileTransferError(
                            f"원격 디렉토리를 생성하지 못했습니다: {current}"
                        ) from exc
            except Exception as exc:
                self.logger.warning(
                    "[경고] 원격 디렉토리 상태 확인 중 오류(%s): %s", current, str(exc)
                )
                raise

    def _remote_file_exists(self, remote_path: str) -> bool:
        """원격 파일 존재 여부 확인"""
        if not self.sftp_client:
            return False
        try:
            self.sftp_client.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def _wait_for_file_completion(
        self, remote_path: str, stability_time: int = 5, max_wait: int = 30
    ) -> bool:
        """
        파일이 완전히 이동/복사되었는지 확인 (파일 크기 안정화 기준)

        Args:
            remote_path: 원격 파일 경로
            stability_time: 파일 크기가 안정화되어야 하는 시간 (초)
            max_wait: 최대 대기 시간 (초)

        Returns:
            파일이 완전히 준비되었는지 여부
        """
        if not self.sftp_client:
            return False
        try:
            self.logger.debug("[정보] 파일 완전성 확인 시작: %s", remote_path)

            start_time = time.time()
            last_size = None
            stable_since = None

            while time.time() - start_time < max_wait:
                try:
                    # 파일 크기 확인
                    stat_result = self.sftp_client.stat(remote_path)
                    current_size = stat_result.st_size

                    if last_size is None:
                        last_size = current_size
                        stable_since = time.time()
                        self.logger.debug(
                            "[정보] 파일 크기 첫 확인: %d bytes", current_size
                        )

                    elif current_size == last_size:
                        # 파일 크기가 동일하면 안정화 시간 확인
                        if stable_since is None:
                            stable_since = time.time()
                        stable_duration = time.time() - stable_since
                        if stable_duration >= stability_time:
                            self.logger.debug(
                                "[성공] 파일 크기 안정화 완료: %d bytes (%.1f초)",
                                current_size,
                                stable_duration,
                            )
                            return True
                        else:
                            self.logger.debug(
                                "[정보] 파일 크기 안정화 중: %d bytes (%.1f초)",
                                current_size,
                                stable_duration,
                            )

                    else:
                        # 파일 크기가 변경되면 안정화 시간 초기화
                        self.logger.debug(
                            "[정보] 파일 크기 변경: %d -> %d bytes",
                            last_size,
                            current_size,
                        )
                        last_size = current_size
                        stable_since = time.time()

                except FileNotFoundError:
                    self.logger.debug(
                        "[정보] 파일이 아직 존재하지 않습니다: %s", remote_path
                    )
                    last_size = None
                    stable_since = None

                time.sleep(1)

            self.logger.warning("[경고] 파일 완전성 확인 시간 초과: %d초", max_wait)
            return False

        except Exception as e:
            self.logger.error("[실패] 파일 완전성 확인 중 오류 발생: %s", str(e))
            return False

    def _verify_download_integrity(self, remote_path: str, local_path: str) -> bool:
        """
        다운로드된 파일의 무결성 확인

        Args:
            remote_path: 원격 파일 경로
            local_path: 로컬 파일 경로

        Returns:
            파일 무결성 확인 결과
        """
        if not self.sftp_client:
            return False
        try:
            # 원격 파일 크기 확인
            remote_stat = self.sftp_client.stat(remote_path)
            remote_size = remote_stat.st_size

            # 로컬 파일 크기 확인
            local_size = Path(local_path).stat().st_size

            if remote_size == local_size:
                self.logger.debug("[성공] 파일 무결성 확인 완료: %d bytes", remote_size)
                return True
            else:
                self.logger.warning(
                    "[경고] 파일 크기 불일치: 원격=%d, 로컬=%d", remote_size, local_size
                )
                return False

        except Exception as e:
            self.logger.error("[실패] 파일 무결성 확인 중 오류 발생: %s", str(e))
            return False

    def _decode_output(self, data: bytes) -> str:
        """
        바이트 데이터를 문자열로 디코딩 (여러 인코딩 시도)

        Args:
            data: 디코딩할 바이트 데이터

        Returns:
            디코딩된 문자열
        """
        if not data:
            return ""

        # 시도할 인코딩 목록 (Windows 환경에서 자주 사용되는 인코딩)
        encodings = ["utf-8", "cp949", "euc-kr", "cp1252", "latin-1"]

        for encoding in encodings:
            try:
                decoded = data.decode(encoding)
                self.logger.debug("[성공] 데이터 디코딩 성공: %s", encoding)
                return decoded
            except UnicodeDecodeError:
                continue

        # 모든 인코딩 시도 실패 시 오류 처리 방식으로 디코딩
        try:
            decoded = data.decode("utf-8", errors="replace")
            self.logger.warning(
                "[경고] UTF-8 디코딩 실패, 문자 대체 방식으로 디코딩합니다."
            )
            return decoded
        except Exception:
            # 최후의 수단: 바이트를 문자열로 표현
            self.logger.warning(
                "[경고] 모든 디코딩 시도 실패, 바이트 표현으로 반환합니다."
            )
            return str(data)
