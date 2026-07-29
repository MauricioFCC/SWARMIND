@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%" || exit /b 1

where mdbook >nul 2>&1
if errorlevel 1 (
    echo mdBook no está instalado en PATH.
    echo.
    echo Instálalo con:
    echo   cargo install mdbook
    echo.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo Compilando la documentación con mdBook...
    mdbook build
    if errorlevel 1 exit /b %errorlevel%
    echo.
    echo Compilación completada.
    exit /b 0
)

if /I "%~1"=="build" (
    echo Compilando la documentación con mdBook...
    mdbook build
    exit /b %errorlevel%
)

if /I "%~1"=="serve" (
    echo Iniciando mdBook en modo servidor...
    mdbook serve --open
    exit /b %errorlevel%
)

echo Uso:
echo   start-mdbook.bat          Compila la documentación
echo   start-mdbook.bat build    Compila la documentación
echo   start-mdbook.bat serve    Sirve la documentación localmente

exit /b 1
