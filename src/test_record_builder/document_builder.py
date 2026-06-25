import fitz  # type: ignore[import-untyped]  # PyMuPDF
import os
import io
from typing import Tuple, Dict, Optional
from PIL import Image

from test_record_builder.logger import setup_logger
from test_record_builder.config import DocumentBuilderConfig, TextConfig

logger = setup_logger("test_record_builder.document_builder")


class TestRecordBuilder:
    def __init__(self, config: DocumentBuilderConfig):
        self.config = config
        self.doc: Optional[fitz.Document] = None

    def open_pdf(self, file_path: str) -> None:
        """PDF 파일을 엽니다."""
        try:
            # secure file preprocessing 파일은 확장자가 제거되어 있을 수 있으므로 filetype 명시
            if not file_path.lower().endswith(".pdf"):
                self.doc = fitz.open(file_path, filetype="pdf")
            else:
                self.doc = fitz.open(file_path)
            logger.debug(f"PDF 파일 열기 완료: {file_path}")
        except Exception as e:
            logger.error(f"PDF 파일 열기 실패 ({file_path}): {e}")
            raise

    def close_pdf(self) -> None:
        """열려있는 PDF 문서를 닫습니다."""
        if self.doc:
            self.doc.close()
            self.doc = None

    def save_pdf(self, output_path: str) -> None:
        """변경사항을 새 파일로 저장합니다."""
        if not self.doc:
            raise RuntimeError("열려있는 PDF 문서가 없습니다.")
        try:
            # 출력 디렉토리 확인 및 생성
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            # PyMuPDF 특성상 가비지 제거(garbage=4), 스트림 압축(deflate=True) 권장
            self.doc.save(output_path, garbage=4, deflate=True)
            logger.debug(f"PDF 저장 완료: {output_path}")
        except Exception as e:
            logger.error(f"PDF 저장 실패 ({output_path}): {e}")
            raise

    def process_document(self, metadata: Dict[str, str], watermark_path: str) -> None:
        """
        문서의 모든 페이지에 대해 필요한 항목(텍스트, 이미지, 바코드)을 삽입합니다.
        
        Args:
            metadata: 파싱된 실행 인자 정보 렌더링용
            watermark_path: 워터마크 이미지 파일 경로
        """
        if not self.doc:
            raise RuntimeError("PDF 문서가 열려있지 않습니다.")
            
        pos = self.config.positions
        total_pages = len(self.doc)

        # 새 문서를 생성하여 여백을 만들면서 기존 콘텐츠 복사
        new_doc = fitz.open()

        page_req_all_yn = metadata.get("PageReqALLYn", "Y")
        try:
            page_req_start_no = int(metadata.get("PageReqStartNo", 0))
            page_req_end_no = int(metadata.get("PageReqEndNo", 0))
        except ValueError:
            page_req_start_no = 0
            page_req_end_no = 0

        # 선택된 페이지 목록 결정 (0-indexed)
        if page_req_all_yn == "N" and page_req_start_no > 0 and page_req_end_no >= page_req_start_no:
            start_idx = max(0, page_req_start_no - 1)
            end_idx = min(total_pages - 1, page_req_end_no - 1)
            pages_to_process = list(range(start_idx, end_idx + 1))
        else:
            pages_to_process = list(range(total_pages))

        actual_total_pages = len(pages_to_process)

        for out_page_idx, old_page_idx in enumerate(pages_to_process):
            old_page = self.doc[old_page_idx]
            
            # 여백이 포함된 새 페이지 생성
            new_page = self._create_page_with_margins(new_doc, old_page, old_page_idx)
            
            # 각 영역 렌더링
            self._render_watermark(new_page, watermark_path, pos.watermark_image_rect)
            self._render_header(new_page, metadata, out_page_idx, actual_total_pages)
            self._render_footer(new_page, metadata)
            self._render_barcode(new_page, metadata)

        # 문서 교체
        self.doc.close()
        self.doc = new_doc

    # ========== 페이지 구성 ==========

    def _create_page_with_margins(
        self, new_doc: fitz.Document, old_page: fitz.Page, page_index: int
    ) -> fitz.Page:
        """기존 페이지를 여백 포함한 새 페이지로 복사"""
        margin_top = 25.0
        margin_bottom = 30.0
        
        new_page = new_doc.new_page(
            width=old_page.rect.width, height=old_page.rect.height
        )
        target_rect = fitz.Rect(
            0, margin_top, old_page.rect.width, old_page.rect.height - margin_bottom
        )
        # 스케일 다운되어 복사됨 (기존 PDF 내용이 target_rect 안에 들어감)
        new_page.show_pdf_page(target_rect, self.doc, page_index)
        return new_page

    # ========== 영역별 렌더링 ==========

    def _render_header(
        self, page: fitz.Page, metadata: Dict[str, str], page_index: int, total_pages: int
    ) -> None:
        """머리글 영역의 모든 텍스트를 삽입"""
        pos = self.config.positions
        templates = pos.text_templates

        # 템플릿 변수 준비
        tpl_vars = {
            **metadata,
            "page": str(page_index + 1),
            "total_pages": str(total_pages),
        }

        # 머리글 필드 목록: (config key, template key)
        header_fields = [
            ("TestReqNo", "TestReqNo"),
            ("StockedAssetCode", "StockedAssetCode"),
            ("PrtReqEmpName", "PrtReqEmpName"),
            ("TestUseKind", "TestUseKind"),
            ("ConfirmEmpName", "ConfirmEmpName"),
            ("ApprovalDate", "ApprovalDate"),
        ]

        for config_key, tpl_key in header_fields:
            rect = getattr(pos, f"{config_key}_rect")
            cfg = getattr(pos, f"{config_key}_text")
            template = templates.get(tpl_key, "")
            
            try:
                text = template.format(**tpl_vars)
            except KeyError as e:
                logger.warning(f"템플릿 변수 누락 ({tpl_key}): {e}")
                text = template

            self._insert_text(page, text, rect, cfg)

    def _render_footer(self, page: fitz.Page, metadata: Dict[str, str]) -> None:
        """바닥글 영역의 텍스트를 삽입"""
        pos = self.config.positions
        templates = pos.text_templates

        reason = metadata.get("RePrtReason", "").strip()
        reason_text = f"/{reason}" if reason else ""
        
        tpl_vars = {**metadata, "reason": reason_text}
        template = templates.get("RePrtCnt", "")
        
        try:
            text = template.format(**tpl_vars)
        except KeyError as e:
            logger.warning(f"바닥글 템플릿 변수 누락: {e}")
            text = template

        self._insert_text(page, text, pos.RePrtCnt_rect, pos.RePrtCnt_text)

    def _render_barcode(self, page: fitz.Page, metadata: Dict[str, str]) -> None:
        """바코드 영역 렌더링"""
        pos = self.config.positions
        templates = pos.text_templates
        
        barcode_str = metadata.get("PrtReqNo", "")
        if not barcode_str:
            return

        template = templates.get("PrtReqNo", "*{PrtReqNo}{PrtReqSeq}*")
        try:
            formatted_text = template.format(**metadata)
        except KeyError:
            formatted_text = f"*{barcode_str}{metadata.get('PrtReqSeq', '')}*"

        self._insert_text(page, formatted_text, pos.PrtReqNo_rect, pos.PrtReqNo_text)

    def _render_watermark(
        self, page: fitz.Page, watermark_path: str, rect: Tuple[float, float, float, float]
    ) -> None:
        """워터마크 이미지를 삽입"""
        if not os.path.exists(watermark_path):
            logger.warning(f"워터마크 이미지 파일 존재하지 않음: {watermark_path}")
            return

        rect_obj = fitz.Rect(*rect)
        if rect_obj.is_empty or not rect_obj.is_valid:
            logger.warning(f"워터마크 출력 위치(Rect)가 잘못되었습니다: {rect_obj}")
            return

        try:
            # 투명도 및 임시 스트림 처리
            opacity = getattr(self.config.positions, "watermark_opacity", 1.0)
            img_stream = None

            with Image.open(watermark_path) as img:
                img_w, img_h = img.size

                if opacity < 1.0:
                    # RGBA 변환
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')

                    # 알파 채널 투명도 비율 적용
                    r, g, b, a = img.split()
                    a = a.point(lambda p: int(p * opacity))
                    img.putalpha(a)

                    # 메모리에 PNG 형식으로 저장 (알파 보존)
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='PNG')
                    img_byte_arr.seek(0)
                    img_stream = img_byte_arr.read()

            # 비율 유지 축소
            scale = min(rect_obj.width / (img_w or 1), rect_obj.height / (img_h or 1))
            new_w = img_w * scale
            new_h = img_h * scale

            # 좌상단 기준 Rect 생성
            tl_rect = fitz.Rect(
                rect_obj.x0, rect_obj.y0, rect_obj.x0 + new_w, rect_obj.y0 + new_h
            )
            
            if img_stream:
                page.insert_image(tl_rect, stream=img_stream, overlay=True, keep_proportion=True)
            else:
                page.insert_image(tl_rect, filename=watermark_path, overlay=True, keep_proportion=True)
        except Exception as e:
            logger.error(f"워터마크 이미지 삽입 실패: {e}")

    # ========== 공통 헬퍼 ==========

    def _ensure_font_on_page(
        self, page: fitz.Page, font_name: str, font_path: str
    ) -> str:
        """
        해당 페이지에 폰트를 등록하고, 사용 가능한 폰트명을 반환합니다.
        
        Returns:
            등록된 폰트명 (실패 시 기본 폰트 "helv")
        """
        if not os.path.exists(font_path):
            # 상대 경로 해결 시도
            from test_record_builder.config import _get_asset_path
            basename = os.path.basename(font_path) if os.sep in font_path or "/" in font_path else font_path
            font_path = _get_asset_path(basename)
        
        if os.path.exists(font_path):
            try:
                page.insert_font(fontname=font_name, fontfile=font_path)
                return font_name
            except Exception as e:
                logger.error(f"폰트 임베딩 실패: {font_path}, {e}")
        else:
            logger.warning(f"폰트 경로를 찾을 수 없습니다: {font_path}, 기본 폰트로 대체됩니다.")
        
        return "helv"

    @staticmethod
    def _normalize_color(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
        """RGB 0-255를 PyMuPDF의 0.0-1.0 범위로 변환"""
        return (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)

    def _insert_text(
        self, page: fitz.Page, text: str, rect: Tuple[float, float, float, float], cfg: TextConfig
    ) -> None:
        """주어진 사각형 박스 내에 텍스트 삽입"""
        if not text:
            return

        # 폰트 결정
        font_path = cfg.font_bold_path if cfg.use_bold_font else cfg.font_path
        font_name = f"{cfg.font_name}_{'b' if cfg.use_bold_font else 'n'}"
        font_used = self._ensure_font_on_page(page, font_name, font_path)

        color = self._normalize_color(cfg.font_color)

        try:
            # 가로 정렬 지원 (left, center, right)
            align_str = getattr(cfg, 'align', 'left').lower()
            align_val = fitz.TEXT_ALIGN_LEFT
            
            x0, y0, x1, y1 = rect
            
            if align_str == "center":
                align_val = fitz.TEXT_ALIGN_CENTER
            elif align_str == "right":
                align_val = fitz.TEXT_ALIGN_RIGHT
                # 사용자 아이디어 활용: 우측 정렬 시 가용 너비(width)를 문서 맨 왼쪽(0.0)까지 열어줌으로써
                # 박스 너비 부족으로 인한 무분별한 줄바꿈 현상을 방지함
                x0 = 0.0

            box_rect = fitz.Rect(x0, y0, x1, y1)
            
            # 좌표 기준이 아닌 폭(Rect)을 기준으로 글씨 박스를 그려 정렬(align)을 적용
            page.insert_textbox(
                box_rect,
                text,
                fontsize=cfg.font_size,
                fontname=font_used,
                color=color,
                align=align_val,
            )
        except Exception as e:
            logger.error(f"텍스트 삽입 중 오류 발생: {text}, {e}")
