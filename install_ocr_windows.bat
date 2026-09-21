@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
  echo [Picture Capture] uv was not found.
  echo Install uv first: https://docs.astral.sh/uv/
  pause
  exit /b 1
)

echo.
echo ============================================================
echo Picture Capture OCR installer
echo PaddleOCR + Google Lens / CPU or NVIDIA GPU

echo ============================================================
echo.
where nvidia-smi >nul 2>&1
if not errorlevel 1 (
  echo Detected NVIDIA GPU / driver:
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>nul
  echo.
)

echo Choose one profile:
echo   1. CPU       - PaddleOCR + Google Lens
echo   2. GPU cu118 - PaddleOCR + Google Lens + PaddlePaddle GPU 3.3.0
echo   3. GPU cu126 - PaddleOCR + Google Lens + PaddlePaddle GPU 3.3.0
echo   4. GPU cu129 - PaddleOCR + Google Lens + PaddlePaddle GPU 3.3.0
echo   5. Lens only - Google Lens only
echo   6. Core only - remove optional OCR profile

echo.
set /p "PC_CHOICE=Selection [1-6]: "

set "PC_EXTRA="
set "PC_GPU_INDEX="
set "PC_EXPECT="

if "%PC_CHOICE%"=="1" (
  set "PC_EXTRA=ocr-cpu"
  set "PC_EXPECT=cpu"
) else if "%PC_CHOICE%"=="2" (
  set "PC_EXTRA=ocr-gpu-cu118"
  set "PC_GPU_INDEX=https://www.paddlepaddle.org.cn/packages/stable/cu118/"
  set "PC_EXPECT=gpu"
) else if "%PC_CHOICE%"=="3" (
  set "PC_EXTRA=ocr-gpu-cu126"
  set "PC_GPU_INDEX=https://www.paddlepaddle.org.cn/packages/stable/cu126/"
  set "PC_EXPECT=gpu"
) else if "%PC_CHOICE%"=="4" (
  set "PC_EXTRA=ocr-gpu-cu129"
  set "PC_GPU_INDEX=https://www.paddlepaddle.org.cn/packages/stable/cu129/"
  set "PC_EXPECT=gpu"
) else if "%PC_CHOICE%"=="5" (
  set "PC_EXTRA=lens"
  set "PC_EXPECT=lens"
) else if "%PC_CHOICE%"=="6" (
  echo.
  echo [1/2] Syncing core environment...
  uv sync --locked
  if errorlevel 1 goto :failed
  if exist ".picture_capture_ocr_extra" del /q ".picture_capture_ocr_extra"
  echo [2/2] Optional OCR profile removed.
  echo.
  echo Core environment is ready. Tesseract, if installed system-wide, is unaffected.
  pause
  exit /b 0
) else (
  echo Invalid selection.
  pause
  exit /b 2
)

echo.
echo [1/4] Syncing Python OCR tools with uv profile: %PC_EXTRA%
uv sync --locked --extra "%PC_EXTRA%"
if errorlevel 1 goto :failed

if defined PC_GPU_INDEX (
  echo.
  echo [2/4] Replacing Paddle runtime with NVIDIA GPU build...
  uv pip uninstall --python ".venv\Scripts\python.exe" paddlepaddle paddlepaddle-gpu >nul 2>&1
  uv pip install --python ".venv\Scripts\python.exe" --index "%PC_GPU_INDEX%" "paddlepaddle-gpu==3.3.0"
  if errorlevel 1 goto :failed
) else (
  echo.
  echo [2/4] Paddle runtime profile does not require a manual GPU install.
)

> ".picture_capture_ocr_extra" echo %PC_EXTRA%

echo.
echo [3/4] Verifying OCR environment...
uv run --locked --extra "%PC_EXTRA%" python scripts\verify_ocr_environment.py --expect "%PC_EXPECT%" --profile "%PC_EXTRA%"
if errorlevel 1 goto :verify_failed

echo.
echo [4/4] Installation complete.
echo Saved OCR profile: %PC_EXTRA%
echo run_windows.bat will reuse this profile automatically.
echo.
pause
exit /b 0

:verify_failed
echo.
echo [Picture Capture] Packages were installed, but verification failed.
echo Review the messages above. The selected profile was saved so you can retry after fixing the driver/runtime issue.
pause
exit /b 3

:failed
echo.
echo [Picture Capture] OCR installation failed.
echo No working profile change is guaranteed. Review the uv error above and retry.
pause
exit /b 1
