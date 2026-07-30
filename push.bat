@echo off
title Swarmind - Push to Drive
cd /d "%~dp0"

:: ── Colors ───────────────────────────────────────────────────────────────
set "ESC="
set "G=%ESC%[32m"
set "C=%ESC%[36m"
set "R=%ESC%[31m"
set "Y=%ESC%[33m"
set "B=%ESC%[34m"
set "W=%ESC%[37m"
set "RESET=%ESC%[0m"

:: ── Banner ───────────────────────────────────────────────────────────────
cls
echo.
echo %B%  █████╗  ██████╗ ███████╗███╗   ██╗████████╗██╗ ██████╗ %RESET%
echo %B% ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██║██╔════╝ %RESET%
echo %B% ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ██║██║      %RESET%
echo %B% ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ██║██║      %RESET%
echo %B% ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ██║╚██████╗ %RESET%
echo %B% ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝ ╚═════╝ %RESET%
echo %C%  Push to Google Drive%RESET%
echo.

:: ── Check dependencies ──────────────────────────────────────────────────
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo %R%  ❌ uv not found. Install from https://github.com/astral-sh/uv%RESET%
    pause
    exit /b 1
)

:: ── Ensure torch with CUDA ──────────────────────────────────────────────
uv run python -c "import torch; assert 'cu' in torch.__version__, 'CPU torch'; print('✅ CUDA torch OK')" 2>nul
if %errorlevel% neq 0 (
    echo %Y%  ⚠️  Installing torch with CUDA 12.4...%RESET%
    uv pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124 --quiet
    if %errorlevel% equ 0 (
        echo %G%  ✅ CUDA torch installed%RESET%
    ) else (
        echo %Y%  ⚠️  CPU torch will be used instead%RESET%
    )
)

:: ── Export to Google Drive ──────────────────────────────────────────────
echo.
echo %B%  📤 Exporting Swarmind to Google Drive...%RESET%
echo.

uv run python scripts/export_to_drive.py
set "EXIT_CODE=%errorlevel%"

echo.
if %EXIT_CODE% equ 0 (
    echo %G%  ✅ Push complete!%RESET%
    echo %W%  📍 $HOME\Mi unidad\DEV\SIDEPROYECT\exports%RESET%
) else (
    echo %R%  ❌ Push failed (exit %EXIT_CODE%)%RESET%
)

echo.
echo %C%  ────────────────────────────────────────────%RESET%
echo %W%  Press any key to close, or close this window.%RESET%
echo %C%  ────────────────────────────────────────────%RESET%
pause >nul
exit /b %EXIT_CODE%
