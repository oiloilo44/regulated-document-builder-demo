#!/usr/bin/env python3
"""시험 기록서 문서 빌더 프로그램 예외 정의

NOTE: PDFFileNotFoundError, InvalidPDFFileError, PageNumberOutOfRangeError,
      ImageFileNotFoundError는 현재 미사용 상태이며, 향후 세분화된 에러 처리 시 활용 예정.
"""


class DocumentBuilderError(Exception):
    """제조/포장 문서 빌더 프로그램 기본 예외"""

    pass


class PDFFileNotFoundError(DocumentBuilderError):
    """PDF 파일을 찾을 수 없을 때 발생하는 예외"""

    pass


class InvalidPDFFileError(DocumentBuilderError):
    """유효하지 않은 PDF 파일일 때 발생하는 예외"""

    pass


class PageNumberOutOfRangeError(DocumentBuilderError):
    """페이지 번호가 범위를 벗어났을 때 발생하는 예외"""

    pass


class ImageFileNotFoundError(DocumentBuilderError):
    """이미지 파일을 찾을 수 없을 때 발생하는 예외"""

    pass


class PDFProcessingError(DocumentBuilderError):
    """PDF 처리 중 발생하는 일반적인 예외"""

    pass
