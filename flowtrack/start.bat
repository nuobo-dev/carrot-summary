@echo off
REM Launch FlowTrack on Windows
cd /d "%~dp0"
if exist venv\Scripts\activate (
    call venv\Scripts\activate
) else (
    echo Setting up FlowTrack for the first time...
    python -m venv venv
    call venv\Scripts\activate
    pip install -r requirements.txt
)
python -m flowtrack.main
