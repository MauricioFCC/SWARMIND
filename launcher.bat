@echo off
title AGENTIC Multi-Agent System
setlocal enabledelayedexpansion

:: ============================================================================
:: AGENTIC Launcher — Multi-Agent Evolutionary Harness
:: ============================================================================
:: Punto de entrada principal. Detecta uv, activa entorno, lanza menu.
:: Compatible con Windows 10/11.
:: ============================================================================

cd /d "%~dp0"
set "ROOT=%cd%"

:: ── Colors ───────────────────────────────────────────────────────────────
set "ESC="
set "R=%ESC%[31m"
set "G=%ESC%[32m"
set "Y=%ESC%[33m"
set "B=%ESC%[34m"
set "M=%ESC%[35m"
set "C=%ESC%[36m"
set "W=%ESC%[37m"
set "RESET=%ESC%[0m"

:: ── Banner ───────────────────────────────────────────────────────────────
:banner
cls
echo.
echo %B%  █████╗  ██████╗ ███████╗███╗   ██╗████████╗██╗ ██████╗ %RESET%
echo %B% ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██║██╔════╝ %RESET%
echo %B% ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ██║██║      %RESET%
echo %B% ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ██║██║      %RESET%
echo %B% ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ██║╚██████╗ %RESET%
echo %B% ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝ ╚═════╝ %RESET%
echo %C%  Multi-Agent Evolutionary Harness v2.0%RESET%
echo %W%  %ROOT%%RESET%
echo.

:: ── Health check ─────────────────────────────────────────────────────────
:check
set "PYTHON_CMD="
where uv >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=uv run python"
    echo %G%  ✅ uv detected%RESET%
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=python"
        echo %Y%  ⚠️  uv not found, using system python%RESET%
    ) else (
        echo %R%  ❌ Python not found! Install Python 3.10+ or uv%RESET%
        echo %Y%     https://github.com/astral-sh/uv%RESET%
        pause
        exit /b 1
    )
)

if exist "%ROOT%\.venv" (
    echo %G%  ✅ Virtual env found%RESET%
) else (
    echo %Y%  ⚠️  No .venv — run: uv sync%RESET%
)

:: ── Menu ─────────────────────────────────────────────────────────────────
:menu
echo.
echo %B%  ╔══════════════════════════════════════╗%RESET%
echo %B%  ║       AGENTIC CONTROL PANEL          ║%RESET%
echo %B%  ╠══════════════════════════════════════╣%RESET%
echo %B%  ║                                      ║%RESET%
echo %B%  ║  %W% 1) 🧪  Run Tests%RESET%                 %B%║%RESET%
echo %B%  ║  %W% 2) 📊  Test Coverage%RESET%             %B%║%RESET%
echo %B%  ║  %W% 3) 🚀  Deploy to All Projects%RESET%    %B%║%RESET%
echo %B%  ║  %W% 4) 📤  Export to Google Drive%RESET%    %B%║%RESET%
echo %B%  ║  %W% 5) 📋  List Tests%RESET%                %B%║%RESET%
echo %B%  ║  %W% 6) 🔧  Lint Code (ruff)%RESET%          %B%║%RESET%
echo %B%  ║  %W% 7) ⚡  GPU Info%RESET%                   %B%║%RESET%
echo %B%  ║  %W% 8) 📦  Export + ZIP%RESET%               %B%║%RESET%
echo %B%  ║  %W% 0)  🚪  Exit%RESET%                     %B%║%RESET%
echo %B%  ║                                      ║%RESET%
echo %B%  ╚══════════════════════════════════════╝%RESET%
echo.
set /p "choice=%C%  › %RESET%"

if "%choice%"=="1" goto run_tests
if "%choice%"=="2" goto run_coverage
if "%choice%"=="3" goto run_deploy
if "%choice%"=="4" goto run_export
if "%choice%"=="5" goto list_tests
if "%choice%"=="6" goto run_lint
if "%choice%"=="7" goto gpu_info
if "%choice%"=="8" goto run_export_zip
if "%choice%"=="0" goto end
goto menu

:: ── Actions ──────────────────────────────────────────────────────────────

:run_tests
cls
echo %B%  🧪 Running Tests (fast: no slow)...%RESET%
echo.
%PYTHON_CMD% -m pytest harness/tests/ -x -q --tb=short -m "not slow"
echo.
echo %G%  ✅ Done%RESET%
pause
goto banner

:run_coverage
cls
echo %B%  📊 Running Coverage...%RESET%
echo.
%PYTHON_CMD% -m pytest harness/tests/ -q --tb=no --cov=harness --cov-config=pyproject.toml
echo.
pause
goto banner

:run_deploy
cls
echo %B%  🚀 Deploying to All Projects...%RESET%
echo.
%PYTHON_CMD% scripts/deploy_all.py
echo.
pause
goto banner

:run_export
cls
echo %B%  📤 Exporting to Google Drive...%RESET%
echo.
%PYTHON_CMD% scripts/export_to_drive.py
echo.
pause
goto banner

:list_tests
cls
echo %B%  📋 Test Files%RESET%
echo.
dir /b "%ROOT%\harness\tests\test_*.py" /o:n
echo.
echo %G%  Total test files listed above%RESET%
pause
goto banner

:run_lint
cls
echo %B%  🔧 Running Ruff Linter...%RESET%
echo.
%PYTHON_CMD% -m ruff check harness/ --select=E,F,W,I,N --ignore=E501
echo.
echo %G%  ✅ Done%RESET%
pause
goto banner

:gpu_info
cls
echo %B%  ⚡ GPU Information%RESET%
echo.
%PYTHON_CMD% -c "from harness.gpu_accel import HAVE_CUDA, DEVICE_NAME, GPU_MEMORY_GB; print(f'GPU Available: {HAVE_CUDA}'); print(f'Device: {DEVICE_NAME}'); print(f'VRAM: {GPU_MEMORY_GB:.1f} GB')"
echo.
pause
goto banner

:run_export_zip
cls
echo %B%  📦 Export to Google Drive + ZIP...%RESET%
echo.
%PYTHON_CMD% scripts/export_to_drive.py
echo.
pause
goto banner

:: ── End ──────────────────────────────────────────────────────────────────
:end
echo.
echo %G%  👋 Goodbye!%RESET%
timeout /t 2 >nul
exit /b 0
