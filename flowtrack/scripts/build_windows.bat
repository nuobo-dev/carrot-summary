@echo off
REM Build CarrotSummary for Windows: .exe + .zip distribution.
REM Usage: scripts\build_windows.bat
REM Output: dist\CarrotSummary.zip

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."

echo ==> Building CarrotSummary for Windows...

cd /d "%PROJECT_DIR%"

REM ── Step 1: Run PyInstaller ────────────────────────────────────────
echo ==> Running PyInstaller...
pyinstaller flowtrack.spec --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

REM Verify the dist\CarrotSummary directory was created
if not exist "dist\CarrotSummary\" (
    echo ERROR: dist\CarrotSummary directory not found.
    exit /b 1
)

echo ==> CarrotSummary executable created successfully.

REM ── Step 2: Create .zip distribution ───────────────────────────────
set "ZIP_PATH=dist\CarrotSummary.zip"

REM Remove existing .zip if present
if exist "%ZIP_PATH%" (
    echo ==> Removing existing CarrotSummary.zip...
    del /f "%ZIP_PATH%"
)

echo ==> Creating CarrotSummary.zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\CarrotSummary\*' -DestinationPath '%ZIP_PATH%' -Force"
if errorlevel 1 (
    echo ERROR: Failed to create CarrotSummary.zip.
    exit /b 1
)

if not exist "%ZIP_PATH%" (
    echo ERROR: CarrotSummary.zip was not created.
    exit /b 1
)

echo ==> Build complete: %ZIP_PATH%
