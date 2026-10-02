"""실제 업무 자료를 사용하지 않는 두 페이지짜리 입력 PDF를 생성합니다."""
from pathlib import Path

import fitz


def main():
    output = Path(__file__).with_name("input.pdf")
    with fitz.open() as document:
        for number in (1, 2):
            page = document.new_page(width=595, height=842)
            page.insert_text((60, 120), "Synthetic test record", fontsize=20)
            page.insert_text((60, 155), f"Demo page {number} / 2 - no production data", fontsize=12)
            page.draw_rect(fitz.Rect(60, 190, 535, 720), color=(0.5, 0.5, 0.5))
        document.save(output)
    print(output)


if __name__ == "__main__":
    main()
