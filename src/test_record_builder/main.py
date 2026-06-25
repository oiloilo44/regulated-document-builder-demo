#!/usr/bin/env python3
"""시험 기록서 문서 빌더 프로그램 진입점"""

import sys
import os
import argparse
import json
from collections import defaultdict
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import shutil

from test_record_builder.logger import setup_logger
from test_record_builder.config import DocumentBuilderConfig, PositionConfig
from test_record_builder.document_builder import TestRecordBuilder
from test_record_builder.secure_file_handler import SecureFileHandler
from test_record_builder.db_updater import DBUpdater
from test_record_builder.storage_handler import StorageHandler

logger = setup_logger("test_record_builder.main")


# ========== 데이터 모델 ==========

REQUIRED_FIELDS = [
    "InputPdfPath", "TestReqNo", "PrtReqNo", "PrtReqSeq", "StockedAssetCode", 
    "PrtReqEmpName", "ConfirmEmpName", "TestUseKind", "RePrtCnt",
    "PageReqALLYn", "PageReqStartNo", "PageReqEndNo"
]

@dataclass
class DocumentMetadata:
    """문서 빌드에 필요한 메타데이터"""
    TestReqNo: str = ""
    StockedAssetCode: str = ""
    PrtReqEmpName: str = ""
    ConfirmEmpName: str = ""
    TestUseKind: str = ""
    ApprovalDate: str = ""
    RePrtCnt: str = ""
    RePrtReason: str = ""
    PrtReqNo: str = ""
    PrtReqSeq: str = ""
    PageReqALLYn: str = ""
    PageReqStartNo: str = ""
    PageReqEndNo: str = ""

    def to_dict(self) -> Dict[str, str]:
        """렌더링용 딕셔너리 변환"""
        from dataclasses import asdict
        return {k: str(v) for k, v in asdict(self).items()}


# ========== CLI 파서 ==========

def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="시험 기록서 PDF 양식에 텍스트 및 로고/바코드를 삽입합니다."
    )
    
    # JSON 옵션 추가
    parser.add_argument("--json", type=str, help="작업 목록이 담긴 JSON 파일 경로 (일괄 처리용)")
    
    # 인자 (json 미사용 시 필수)
    parser.add_argument("InputPdfPath", nargs="?", default=None, help="원본 PDF 파일 경로 (storage)")
    parser.add_argument("TestReqNo", nargs="?", default=None, help="관리번호")
    parser.add_argument("PrtReqNo", nargs="?", default=None, help="관리번호2 (바코드용)")
    parser.add_argument("PrtReqSeq", nargs="?", default=None, help="DB 업데이트 시 사용할 일련번호")
    parser.add_argument("StockedAssetCode", nargs="?", default=None, help="제조/입고번호")
    parser.add_argument("PrtReqEmpName", nargs="?", default=None, help="요청자")
    parser.add_argument("ConfirmEmpName", nargs="?", default=None, help="승인자")
    parser.add_argument("TestUseKind", nargs="?", default=None, help="용도")
    parser.add_argument("ApprovalDate", nargs="?", default=None, help="승인일자 (기본값 설정 가능)")
    parser.add_argument("RePrtCnt", nargs="?", default=None, help="출력횟수")
    parser.add_argument("RePrtReason", nargs="?", default="", help="재출력 사유 (선택)")
    parser.add_argument("PageReqALLYn", nargs="?", default="Y", help="전체 페이지 출력 여부 (Y/N)")
    parser.add_argument("PageReqStartNo", nargs="?", default="0", help="시작 페이지 번호")
    parser.add_argument("PageReqEndNo", nargs="?", default="0", help="종료 페이지 번호")
    
    # 옵션
    parser.add_argument("--page", type=int, help="특정 페이지만 처리 (0부터 시작)")
    parser.add_argument("--verbose", action="store_true", help="상세 로그 출력")
    
    parsed = parser.parse_args(args)
    return parsed


# ========== 파이프라인 단계 ==========

def _load_layout_config(config: DocumentBuilderConfig) -> None:
    """외부 레이아웃 설정(JSON)이 있으면 config에 로드"""
    layout_conf_path = os.path.join(os.getcwd(), "layout_config.json")
    if os.path.exists(layout_conf_path):
        loaded_pos = PositionConfig.load_json(layout_conf_path)
        if loaded_pos:
            config.positions = loaded_pos
            logger.debug(f"레이아웃 설정 로드 완료: {layout_conf_path}")


def _copy_from_storage(input_pdf_path: str, storage_handler: StorageHandler) -> str:
    """storage에서 PDF 파일을 로컬로 복사"""
    logger.debug(f"storage 워크플로우: 지정된 파일 경로에서 복사를 시작합니다. ({input_pdf_path})")
    local_temp_dir = os.path.join(os.getcwd(), "output", "temp_downloads")
    return storage_handler.copy_to_local(input_pdf_path, local_temp_dir)


def _prepare_secure_file_if_needed(
    input_pdf: str, secure_file_handler: SecureFileHandler, verbose: bool = False
) -> str:
    """secure file이 활성화된 경우 secure file preprocessing를 수행하고, 해제된 파일 경로를 반환"""
    if os.getenv("SECURE_FILE_ENABLED", "false").lower() != "true":
        return input_pdf
        
    logger.debug("secure file preprocessing 시도 중...")
    import time
    group_key = f"secure_batch_{int(time.time() * 1000)}"
    
    local_secure_dir = os.path.join(os.getcwd(), "output", "temp_secure_file")
    os.makedirs(local_secure_dir, exist_ok=True)
    
    prep_res = secure_file_handler.prepare_files_batch(
        [(input_pdf, group_key)], local_base_dir=local_secure_dir
    )
    
    if group_key in prep_res and prep_res[group_key]:
        result = prep_res[group_key]
        logger.debug(f"secure file preprocessing 성공: {result}")
        return result
    
    raise RuntimeError("secure file preprocessing 결과(로컬 경로)를 받지 못했습니다.")


def _build_document(
    input_pdf: str, original_filename: str, metadata: DocumentMetadata, config: DocumentBuilderConfig
) -> str:
    """PDF 문서 빌드를 수행하고 출력 파일 경로를 반환"""
    builder = TestRecordBuilder(config)
    
    try:
        builder.open_pdf(input_pdf)
        
        watermark_path = config.resources.watermark_image_path
        builder.process_document(metadata.to_dict(), watermark_path)
        
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = original_filename.replace('.pdf', '')
        
        # 중복 방지를 위해 파일명에 PrtReqNo와 PrtReqSeq 포함
        prt_req_no = metadata.PrtReqNo if metadata.PrtReqNo else "no_req_no"
        prt_req_seq = metadata.PrtReqSeq if metadata.PrtReqSeq else "no_seq"
        
        output_file = os.path.join(
            "output",
            f"{base_name}_{prt_req_no}_{prt_req_seq}_{timestamp_str}_modified.pdf",
        )
        builder.save_pdf(output_file)
        logger.debug(f"작업 완료: 출력 파일 {output_file}")
        return output_file
    finally:
        builder.close_pdf()


def _copy_to_storage(output_file: str, storage_handler: StorageHandler) -> str:
    """완료된 파일을 storage로 업로드하고 storage 경로를 반환"""
    logger.debug("완료된 파일을 storage로 업로드합니다...")
    return storage_handler.copy_to_storage(output_file)


def _update_db_if_needed(
    output_file: str, input_pdf: str, prt_req_no: str, prt_req_seq: str, db_updater: DBUpdater
) -> None:
    """DB 업데이트가 활성화된 경우 출력 경로를 DB에 업데이트"""
    if os.getenv("DB_UPDATE_ENABLED", "false").lower() != "true":
        return
    
    output_filename = os.path.basename(output_file)
    output_dir_path = os.path.dirname(os.path.abspath(output_file))
    
    success = db_updater.update_pdf_output_path(
        prt_req_no=prt_req_no,
        prt_req_seq=prt_req_seq,
        input_pdf_path=input_pdf,
        output_filename=output_filename,
        output_dir_path=output_dir_path,
    )
    
    if success:
        logger.debug("DB 업데이트 완료")
    else:
        logger.warning("DB 업데이트가 일부 조건을 만족하지 않아 진행되지 않았거나 실패했습니다.")


# ========== 메인 진입점 ==========

def _cleanup_old_files() -> None:
    """output 폴더 정책에 따라 오래된 파일 및 임시 폴더를 정리합니다."""
    # .env 파일에서 보관 기간을 가져옵니다. 기본값은 7일.
    try:
        days = int(os.getenv("CLEANUP_RETENTION_DAYS", "7"))
    except ValueError:
        days = 7
        
    output_dir = os.path.join(os.getcwd(), "output")
    if not os.path.exists(output_dir):
        return

    try:
        # 1. 임시 폴더는 조건(날짜) 없이 통째로 비우기
        temp_dirs = ["temp_downloads", "temp_secure_file"]
        for temp_name in temp_dirs:
            temp_path = os.path.join(output_dir, temp_name)
            if os.path.exists(temp_path):
                shutil.rmtree(temp_path, ignore_errors=True)
                logger.debug(f"임시 폴더 비우기 완료: {temp_path}")
            # 다음 작업을 위해 폴더는 다시 생성해 둡니다.
            os.makedirs(temp_path, exist_ok=True)

        # 2. 최종 출력 파일들은 생성일자(ctime) 기준으로 보관 기간 경과 시 삭제
        now = datetime.now()
        cutoff = now.timestamp() - (days * 86400) # days의 초
        
        deleted_count = 0
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    ctime = os.path.getctime(file_path)
                    if ctime < cutoff:
                        os.remove(file_path)
                        deleted_count += 1
                        logger.debug(f"오래된 파일 삭제 (생성 시간 기준): {file_path}")
                except Exception as e:
                    logger.debug(f"파일 삭제 실패 ({file_path}): {e}")
                    
        if deleted_count > 0:
            logger.info(f"보관 기간({days}일)이 지난 예전 출력 파일 {deleted_count}개 삭제 완료")
    except Exception as e:
        logger.warning(f"오래된 파일 정리 중 오류 발생: {e}")


def main(args: Optional[List[str]] = None) -> int:
    parsed_args = parse_args(args)
    
    if parsed_args.verbose:
        import logging
        for name, logger_obj in logging.Logger.manager.loggerDict.items():
            if name.startswith('test_record_builder') and isinstance(logger_obj, logging.Logger):
                logger_obj.setLevel(logging.DEBUG)
                for handler in logger_obj.handlers:
                    handler.setLevel(logging.DEBUG)
        
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled (All loggers and handlers set to DEBUG)")
        
    logger.info("시험 기록서 통합 빌더 시작...")

    # 구동 시마다 오래된 임시/출력 파일 정리
    _cleanup_old_files()

    tasks = []
    if parsed_args.json:
        try:
            with open(parsed_args.json, 'r', encoding='utf-8') as f:
                tasks = json.load(f)
            logger.info(f"JSON 파일 로드 완료: {len(tasks)}개의 작업 발견")
        except Exception as e:
            logger.error(f"JSON 파일 읽기 실패: {e}")
            return 1
    else:
        # 단건 실행을 파이프라인 호환용 리스트(1개)로 변환
        logger.debug(
            f"단건 파라미터 처리: 파일경로={parsed_args.InputPdfPath}, "
            f"관리번호={parsed_args.TestReqNo}, 바코드={parsed_args.PrtReqNo}"
        )
        tasks = [{
            "InputPdfPath": parsed_args.InputPdfPath,
            "TestReqNo": parsed_args.TestReqNo,
            "PrtReqNo": parsed_args.PrtReqNo,
            "PrtReqSeq": parsed_args.PrtReqSeq,
            "StockedAssetCode": parsed_args.StockedAssetCode,
            "PrtReqEmpName": parsed_args.PrtReqEmpName,
            "ConfirmEmpName": parsed_args.ConfirmEmpName,
            "TestUseKind": parsed_args.TestUseKind,
            "ApprovalDate": parsed_args.ApprovalDate,
            "RePrtCnt": parsed_args.RePrtCnt,
            "RePrtReason": parsed_args.RePrtReason,
            "PageReqALLYn": parsed_args.PageReqALLYn,
            "PageReqStartNo": parsed_args.PageReqStartNo,
            "PageReqEndNo": parsed_args.PageReqEndNo,
        }]

    # 설정 로드
    config = DocumentBuilderConfig()
    _load_layout_config(config)

    # 핸들러 초기화
    secure_file_handler = SecureFileHandler(config)
    db_updater = DBUpdater(config.db)
    storage_handler = StorageHandler(config.storage)

    total_success = 0
    total_failed = 0

    # 작업 그룹화 (InputPdfPath 기준) 및 필수 요소 검토
    grouped_tasks = defaultdict(list)

    for idx, task in enumerate(tasks):
        # JSON 데이터 필수 키 검증 (빈 문자열이거나 None인 경우 누락으로 간주)
        missing = [key for key in REQUIRED_FIELDS if task.get(key) is None or str(task.get(key)).strip() == ""]
        if missing:
            logger.error(f"[작업 #{idx+1} 스킵] 필수 항목 누락: {', '.join(missing)} / 데이터: {task}")
            total_failed += 1
            continue
            
        input_pdf = task.get("InputPdfPath")
        grouped_tasks[input_pdf].append(task)

    # 파이프라인 실행
    for input_pdf_path, sub_tasks in grouped_tasks.items():
        logger.info(f"--- 파일 그룹 시작: {input_pdf_path} (총 {len(sub_tasks)}건) ---")
        try:
            # 1. storage 다운로드 (원본 파일 단위로 한 번만)
            downloaded_pdf = _copy_from_storage(input_pdf_path, storage_handler)
            original_filename = os.path.basename(downloaded_pdf)
            
            # 2. secure file preprocessing (필요 시, 원본 단위로 한 번만)
            prepared_pdf = _prepare_secure_file_if_needed(downloaded_pdf, secure_file_handler, parsed_args.verbose)
            
            # 3. 개별 문서 빌드 반복 루프
            for task in sub_tasks:
                try:
                    # 메타데이터 구성 (None 안전하게 문자열 변환)
                    def get_val(key):
                        val = task.get(key)
                        return str(val) if val is not None else ""

                    p_date = get_val("ApprovalDate")
                    if not p_date:
                        p_date = datetime.now().strftime("%Y-%m-%d")

                    metadata = DocumentMetadata(
                        TestReqNo=get_val("TestReqNo"),
                        StockedAssetCode=get_val("StockedAssetCode"),
                        PrtReqEmpName=get_val("PrtReqEmpName"),
                        ConfirmEmpName=get_val("ConfirmEmpName"),
                        TestUseKind=get_val("TestUseKind"),
                        ApprovalDate=p_date,
                        RePrtCnt=get_val("RePrtCnt"),
                        RePrtReason=get_val("RePrtReason"),
                        PrtReqNo=get_val("PrtReqNo"),
                        PrtReqSeq=get_val("PrtReqSeq"),
                        PageReqALLYn=get_val("PageReqALLYn"),
                        PageReqStartNo=get_val("PageReqStartNo"),
                        PageReqEndNo=get_val("PageReqEndNo"),
                    )
                    
                    logger.info(f"개별 문서 빌드 시작: 관리번호={metadata.TestReqNo}, 바코드={metadata.PrtReqNo}, 일련번호={metadata.PrtReqSeq}")
                    
                    # 문서 빌드
                    output_file = _build_document(prepared_pdf, original_filename, metadata, config)
                    
                    # storage 업로드 (저장된 새 경로를 반환받음)
                    output_file = _copy_to_storage(output_file, storage_handler)
                    
                    # DB 업데이트 (단건마다 업데이트 진행)
                    _update_db_if_needed(output_file, downloaded_pdf, metadata.PrtReqNo, metadata.PrtReqSeq, db_updater)
                    
                    total_success += 1
                except Exception as e:
                    # 개별 오류 시 작업 전체를 멈추지 않고 다음 작업 수행 (Skip on Error)
                    logger.error(f"작업 오류 발생 (바코드: {task.get('PrtReqNo')}, 건너뜀): {e}", exc_info=parsed_args.verbose)
                    total_failed += 1
                    
        except Exception as e:
            logger.error(f"다운로드 또는 secure file preprocessing 실패로 인해 전체 그룹 스킵 ({input_pdf_path}): {e}", exc_info=parsed_args.verbose)
            total_failed += len(sub_tasks)

    logger.info(f"--- 전체 작업 완료: 성공 {total_success}건, 실패 {total_failed}건 ---")
    return 1 if total_failed > 0 and total_success == 0 else 0

if __name__ == "__main__":
    sys.exit(main())
