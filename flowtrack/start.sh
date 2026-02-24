#!/bin/bash
# Launch CarrotSummary on Mac
cd "$(dirname "$0")"
source venv/bin/activate 2>/dev/null || {
    echo "Setting up CarrotSummary for the first time..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
}
python -m flowtrack.main
