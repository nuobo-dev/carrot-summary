@echo off
REM Build FlowTrack for Windows: .exe + .zip distribution.
REM Usage: scripts\build_windows.bat
REM Output: dist\FlowTrack.zip

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."

echo ==> Building FlowTrack for Windows...

cd /d "%PROJECT_DIR%"

REM ── Step 1: Run PyInstaller ────────────────────────────────────────
echo ==> Running PyInstaller...
pyinstaller flowtrack.spec --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

REM Verify the dist\FlowTrack directory was created
if not exist "dist\FlowTrack\" (
    echo ERROR: dist\FlowTrack directory not found.
    exit /b 1
)

echo ==> FlowTrack executable created successfully.

REM ── Step 2: Create .zip distribution ───────────────────────────────
set "ZIP_PATH=dist\FlowTrack.zip"

REM Remove existing .zip if present
if exist "%ZIP_PATH%" (
    echo ==> Removing existing FlowTrack.zip...
    del /f "%ZIP_PATH%"
)

echo ==> Creating FlowTrack.zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\FlowTrack\*' -DestinationPath '%ZIP_PATH%' -Force"
if errorlevel 1 (
    echo ERROR: Failed to create FlowTrack.zip.
    exit /b 1
)

if not exist "%ZIP_PATH%" (
    echo ERROR: FlowTrack.zip was not created.
    exit /b 1
)

echo ==> Build complete: %ZIP_PATH%
