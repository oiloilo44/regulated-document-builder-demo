@echo off
REM PDF Layout Config Editor 실행 스크립트

echo [1/1] Starting GUI Editor...
uv run python src/test_record_builder/gui_editor.py

if %errorlevel% neq 0 (
    echo [ERROR] Failed to start GUI Editor.
    pause
    exit /b %errorlevel%
)
