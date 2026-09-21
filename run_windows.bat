@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
  echo [Picture Capture] uv was not found. Install it from https://docs.astral.sh/uv/
  pause
  exit /b 1
)

set "PC_OCR_EXTRA="
if exist ".picture_capture_ocr_extra" (
  set /p PC_OCR_EXTRA=<".picture_capture_ocr_extra"
)

if defined PC_OCR_EXTRA (
  echo [Picture Capture] Starting with uv project environment + OCR profile: %PC_OCR_EXTRA%
  uv run --locked --extra "%PC_OCR_EXTRA%" python run.py
) else (
  echo [Picture Capture] Starting with uv project environment...
  uv run --locked python run.py
)

if errorlevel 1 (
  echo.
  echo [Picture Capture] If uv reports that its version is too old, run: uv self update
  echo [Picture Capture] To install or change OCR components, run: install_ocr_windows.bat
  pause
)
