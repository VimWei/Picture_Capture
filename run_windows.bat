@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
  echo [Picture Capture] uv was not found. Install it from https://docs.astral.sh/uv/
  pause
  exit /b 1
)

echo [Picture Capture] Starting with uv project environment...
uv run --locked python run.py
if errorlevel 1 (
  echo.
  echo [Picture Capture] If uv reports that its version is too old, run: uv self update
  pause
)
