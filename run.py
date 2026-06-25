import os
import sys

# src 디렉터리를 sys.path에 추가하여 런타임에 모듈들을 찾을 수 있도록 함
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.test_record_builder.main import main

if __name__ == "__main__":
    sys.exit(main())
