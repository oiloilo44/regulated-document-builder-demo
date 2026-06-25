#!/usr/bin/env python3
"""secure file preprocessing 핸들러 모듈"""

import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from .config import DocumentBuilderConfig
from .ssh_handler import SSHHandler
from .exceptions import DocumentBuilderError
from .logger import setup_simple_logger


class SecureFileHandlerError(DocumentBuilderError):
    """secure file 핸들러 오류"""

    pass


class SecureFileHandler:
    """secure file preprocessing 핸들러 클래스"""

    def __init__(self, config: Optional[DocumentBuilderConfig] = None):
        """
        secure file 핸들러 초기화

        Args:
            config: 설정 객체 (None이면 기본 설정 사용)
        """
        self.config = config or DocumentBuilderConfig()
        self.logger = setup_simple_logger(__name__)
        self.logger.debug("[성공] secure file 핸들러가 초기화되었습니다.")

    # ========== Public Methods ==========

    def validate_configuration(self) -> None:
        """secure file 관련 설정 유효성 검증"""
        try:
            # SSH 설정 검증
            if not self.config.ssh.hostname:
                raise SecureFileHandlerError("SSH 호스트명이 설정되지 않았습니다")

            if not self.config.ssh.username:
                raise SecureFileHandlerError("SSH 사용자명이 설정되지 않았습니다")

            if not self.config.ssh.password and not self.config.ssh.private_key_path:
                raise SecureFileHandlerError("SSH 인증 정보가 설정되지 않았습니다")

            # secure file 설정 검증
            if not self.config.secure_file.input_path:
                raise SecureFileHandlerError("secure file input 경로가 설정되지 않았습니다")

            if not self.config.secure_file.output_path:
                raise SecureFileHandlerError("secure file output 경로가 설정되지 않았습니다")

            self.logger.debug("[성공] secure file 설정 유효성 검증 완료")

        except Exception as e:
            self.logger.error("[실패] secure file 설정 유효성 검증 실패: %s", str(e))
            raise

    def prepare_files_batch(
        self, pdf_files: List[Tuple[str, str]], local_base_dir: Optional[str] = None
    ) -> Dict[str, str]:
        """
        여러 PDF 파일에서 secure file을 배치로 해제하는 메서드

        Args:
            pdf_files: (파일경로, 그룹키) 튜플의 리스트
                      예: [("/path/file1.pdf", "MAS1210001:MBR-21001"), ...]

        Returns:
            {그룹키: secure file해제된_파일경로} 딕셔너리
        """
        if not pdf_files:
            return {}

        try:
            self.logger.debug("[시작] 배치 secure file preprocessing - 파일 수: %d개", len(pdf_files))

            # 배치 업로드 및 secure file preprocessing 대기
            prepared_files = self._batch_upload_and_wait_for_secure_file_removal(pdf_files, local_base_dir=local_base_dir)

            self.logger.debug(
                "[성공] 배치 secure file preprocessing 완료 - 처리된 파일 수: %d개", len(prepared_files)
            )
            return prepared_files

        except Exception as e:
            self.logger.error("[실패] 배치 secure file preprocessing 중 오류 발생: %s", str(e))
            raise SecureFileHandlerError(f"배치 secure file preprocessing 중 오류 발생: {str(e)}")

    # ========== Private Methods - Batch Processing ==========

    def _batch_upload_and_wait_for_secure_file_removal(
        self, pdf_files: List[Tuple[str, str]], local_base_dir: Optional[str] = None
    ) -> Dict[str, str]:
        """
        배치 파일 업로드 후 secure file preprocessing 대기

        Args:
            pdf_files: (파일경로, 그룹키) 튜플의 리스트

        Returns:
            {그룹키: secure file해제된_파일경로} 딕셔너리
        """
        try:
            # SSH 연결 (한 번만)
            with SSHHandler(self.config.ssh, self.config.secure_file) as ssh:
                # 1단계: 모든 파일 업로드
                upload_info = self._batch_upload_files(ssh, pdf_files)

                # 2단계: 병렬 secure file preprocessing 대기
                prepared_files = self._batch_wait_for_secure_file_removal(ssh, upload_info, local_base_dir=local_base_dir)

                return prepared_files

        except Exception as e:
            self.logger.error("[실패] 배치 secure file preprocessing 프로세스 중 오류 발생: %s", str(e))
            raise SecureFileHandlerError(f"배치 secure file preprocessing 프로세스 중 오류 발생: {str(e)}")

    def _batch_upload_files(
        self, ssh: SSHHandler, pdf_files: List[Tuple[str, str]]
    ) -> List[Dict]:
        """
        모든 파일을 배치로 업로드

        Args:
            ssh: SSH 핸들러
            pdf_files: (파일경로, 그룹키) 튜플의 리스트

        Returns:
            업로드 정보 리스트 [{"group_key": str, "file_path": str, "timestamp": int, "file_name": str}, ...]
        """
        upload_info = []

        self.logger.debug("[시작] 배치 업로드 - 파일 수: %d개", len(pdf_files))

        for pdf_path, group_key in pdf_files:
            try:
                # 파일명 및 타임스탬프 생성
                file_name = Path(pdf_path).name
                timestamp = int(time.time() * 1000000)  # 마이크로초 단위로 더 고유하게
                remote_input_file = (
                    f"{self.config.secure_file.input_path}/{timestamp}_{file_name}"
                )

                self.logger.debug("[정보] 업로드: %s (그룹: %s)", file_name, group_key)
                ssh.upload_file(pdf_path, remote_input_file)

                upload_info.append(
                    {
                        "group_key": group_key,
                        "file_path": pdf_path,
                        "timestamp": timestamp,
                        "file_name": file_name,
                        "remote_input_file": remote_input_file,
                    }
                )

                # 업로드 간 잠시 대기 (서버 과부하 방지)
                time.sleep(0.1)

            except Exception as e:
                self.logger.error("[실패] 파일 업로드 실패: %s - %s", pdf_path, str(e))
                # 개별 파일 실패 시 해당 파일만 스킵하고 계속 진행
                continue

        self.logger.debug(
            "[성공] 배치 업로드 완료 - 성공한 파일 수: %d개", len(upload_info)
        )
        return upload_info

    def _batch_wait_for_secure_file_removal(
        self,
        ssh: SSHHandler,
        upload_info: List[Dict],
        local_base_dir: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        순차적으로 secure file preprocessing 대기 (SSH 연결 안정성을 위해 병렬 처리 제거)

        Args:
            ssh: SSH 핸들러
            upload_info: 업로드 정보 리스트

        Returns:
            {그룹키: secure file해제된_파일경로} 딕셔너리
        """
        if not upload_info:
            return {}

        self.logger.debug("[시작] 배치 secure file preprocessing 대기 - 파일 수: %d개", len(upload_info))

        prepared_files = {}
        completed_count = 0

        # 순차적으로 각 파일 처리
        for info in upload_info:
            try:
                self.logger.debug(
                    "[정보] secure file preprocessing 대기 (%d/%d): %s",
                    completed_count + 1,
                    len(upload_info),
                    info["file_name"],
                )

                local_file_path = self._wait_for_single_secure_file_removal(ssh, info, local_base_dir=local_base_dir)
                prepared_files[info["group_key"]] = local_file_path
                completed_count += 1

                self.logger.debug(
                    "[성공] secure file preprocessing 완료 (%d/%d): %s",
                    completed_count,
                    len(upload_info),
                    info["file_name"],
                )

            except Exception as e:
                self.logger.error(
                    "[실패] secure file preprocessing 실패: %s - %s", info["file_name"], str(e)
                )
                # 개별 파일 실패 시 해당 파일만 스킵하고 계속 진행
                continue

        self.logger.debug(
            "[성공] 배치 secure file preprocessing 완료 - 성공한 파일 수: %d/%d개",
            len(prepared_files),
            len(upload_info),
        )
        return prepared_files

    def _wait_for_single_secure_file_removal(self, ssh: SSHHandler, info: Dict, local_base_dir: Optional[str] = None) -> str:
        """
        단일 파일의 secure file preprocessing 대기

        Args:
            ssh: SSH 핸들러
            info: 업로드 정보 딕셔너리

        Returns:
            secure file preprocessing된 파일의 로컬 경로
        """
        timestamp = info["timestamp"]
        file_name = info["file_name"]

        expected_output_file = f"{self.config.secure_file.output_path}/{timestamp}_{file_name}"
        # secure file 재적용 방지를 위해 확장자 제거
        file_name_without_ext = file_name.replace('.pdf', '')
        temp_prefix = self.config.secure_file.temp_prefix
        if local_base_dir:
            local_output_file = os.path.join(local_base_dir, f"{temp_prefix}{timestamp}_{file_name_without_ext}")
        else:
            local_output_file = f"{temp_prefix}{timestamp}_{file_name_without_ext}"

        start_time = time.time()
        file_found = False

        while time.time() - start_time < self.config.secure_file.max_wait_time:
            # 원격 파일 존재 확인
            if ssh.file_exists(expected_output_file):
                if not file_found:
                    file_found = True

                try:
                    # 파일 다운로드 시도
                    ssh.download_file(
                        expected_output_file,
                        local_output_file,
                        max_retries=self.config.secure_file.max_download_retries,
                        retry_delay=self.config.secure_file.download_retry_delay,
                    )

                    # 다운로드 성공 시 원격 파일 정리
                    self._cleanup_remote_files(
                        ssh, expected_output_file, info["remote_input_file"]
                    )

                    return local_output_file

                except Exception:
                    # 다운로드 실패 시 잠시 대기 후 재시도
                    time.sleep(self.config.secure_file.polling_interval)
                    continue

            time.sleep(self.config.secure_file.polling_interval)

        # 시간 초과
        elapsed_time = int(time.time() - start_time)
        if file_found:
            raise SecureFileHandlerError(
                f"secure file preprocessing된 파일 다운로드 실패: {expected_output_file} (경과 시간: {elapsed_time}초)"
            )
        else:
            raise SecureFileHandlerError(
                f"secure file preprocessing 대기 시간 초과: {file_name} (경과 시간: {elapsed_time}초)"
            )

    # ========== Private Methods - File Management ==========

    def _cleanup_remote_files(self, ssh: SSHHandler, *file_paths: str) -> None:
        """
        원격 파일들을 개별적으로 정리 (재시도 로직 포함)

        Args:
            ssh: SSH 핸들러
            *file_paths: 삭제할 원격 파일 경로들
        """
        deleted_files = []
        failed_files = []

        for file_path in file_paths:
            success = self._delete_remote_file_with_retries(ssh, file_path)

            if success:
                deleted_files.append(file_path)
            else:
                failed_files.append(file_path)

        # 결과 요약 로그
        total_files = len(file_paths)
        if deleted_files and not failed_files:
            self.logger.debug(
                "[성공] 원격 파일 정리 완료: %d개 파일 모두 삭제 성공", total_files
            )
        elif deleted_files and failed_files:
            self.logger.warning(
                "[경고] 원격 파일 정리 부분 완료: %d/%d개 파일 삭제 성공",
                len(deleted_files),
                total_files,
            )
        elif failed_files:
            self.logger.warning(
                "[실패] 원격 파일 정리 실패: %d개 파일 삭제 실패", len(failed_files)
            )

    def _delete_remote_file_with_retries(
        self,
        ssh: SSHHandler,
        file_path: str,
        max_retries: int = 3,
        base_retry_delay: int = 2,
    ) -> bool:
        """원격 파일 삭제를 재시도하며 수행"""

        delay = base_retry_delay

        for attempt in range(1, max_retries + 1):
            try:
                # 삭제 전 파일 존재 여부 확인
                if not ssh.file_exists(file_path):
                    self.logger.debug(
                        "[정보] 원격 파일이 이미 존재하지 않습니다: %s",
                        Path(file_path),
                    )
                    return True

                if attempt > 1:
                    self.logger.debug(
                        "[정보] 원격 파일 삭제 재시도 %d/%d: %s",
                        attempt,
                        max_retries,
                        Path(file_path),
                    )

                normalized_path = file_path.replace("/", "\\")
                self.logger.debug("[정보] 정규화된 경로: %s", normalized_path)

                powershell_cmd = (
                    "powershell.exe -Command \"Remove-Item -Path "
                    f"'{normalized_path}' -Force -ErrorAction SilentlyContinue\""
                )

                stdout, stderr, exit_code = ssh.execute_command(powershell_cmd)

                if exit_code != 0:
                    self.logger.debug(
                        "[정보] PowerShell 삭제 실패, del 명령을 시도합니다: %s",
                        stderr,
                    )
                    fallback_cmd = f'del /f /q "{normalized_path}" 2>nul'
                    stdout, stderr, exit_code = ssh.execute_command(fallback_cmd)
                else:
                    fallback_cmd = None

                if exit_code == 0 and not ssh.file_exists(file_path):
                    self.logger.debug("[성공] 원격 파일 삭제 완료: %s", Path(file_path))
                    return True

                if exit_code != 0:
                    self.logger.warning(
                        "[경고] 원격 파일 삭제 명령 실패 (exit_code: %d): %s",
                        exit_code,
                        Path(file_path),
                    )
                    self.logger.debug("[정보] 사용된 명령: %s", powershell_cmd)
                    if fallback_cmd:
                        self.logger.debug("[정보] 대체 명령: %s", fallback_cmd)
                    if stderr:
                        self.logger.debug("[정보] 삭제 오류 메시지: %s", stderr)
                    if stdout:
                        self.logger.debug("[정보] 삭제 출력: %s", stdout)
                else:
                    self.logger.warning(
                        "[경고] 원격 파일 삭제 실패 (파일이 여전히 존재함): %s",
                        Path(file_path),
                    )
                    if stderr:
                        self.logger.debug("[정보] 삭제 오류 메시지: %s", stderr)
                    if stdout:
                        self.logger.debug("[정보] 삭제 출력: %s", stdout)

            except Exception as exc:
                self.logger.warning(
                    "[경고] 원격 파일 삭제 중 예외 발생: %s - %s",
                    Path(file_path),
                    str(exc),
                )

            if attempt < max_retries:
                self.logger.debug("[정보] %d초 후 재시도합니다...", delay)
                time.sleep(delay)
                delay *= 2

        self.logger.warning(
            "[경고] 원격 파일 삭제 재시도를 모두 소진했습니다: %s",
            Path(file_path),
        )
        return False
