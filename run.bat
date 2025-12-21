@echo off
REM Launch KaivosAI in the current command prompt window
REM Compatible with Windows CMD

setlocal enabledelayedexpansion

REM Get script directory
for %%I in ("%~dp0.") do set "SCRIPT_DIR=%%~fI"
cd /d "%SCRIPT_DIR%" || exit /b 1

REM Check if virtual environment exists
if not exist ".venv" (
    echo.
    echo [!] Virtual environment not found
    echo Run: python -m venv .venv
    echo.
    exit /b 1
)

REM Activate virtual environment
call .venv\Scripts\activate.bat
if !errorlevel! neq 0 (
    echo [!] Failed to activate virtual environment
    exit /b 1
)

REM Check if Textual is installed
python -c "import textual" >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo [!] Textual not installed
    echo Run: pip install textual
    echo.
    exit /b 1
)

REM Launch KaivosAI
echo.
echo Starting KaivosAI...
echo.
python kaivosai.py
set EXIT_CODE=!errorlevel!

if !EXIT_CODE! neq 0 (
    echo.
    echo [!] Program exited with code !EXIT_CODE!
    echo.
)

endlocal
exit /b !EXIT_CODE!
