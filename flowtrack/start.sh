#!/bin/bash
# Launch CarrotSummary
# Usage: ./start.sh
# Dashboard opens at http://localhost:5555
cd "$(dirname "$0")"

# Activate venv (try both common names)
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "🥕 First-time setup — creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
fi

# Always ensure deps are installed
python3 -c "import flask" 2>/dev/null || {
    echo "🥕 Installing dependencies..."
    pip install -r requirements.txt -q
}

echo "🥕 Starting CarrotSummary..."
echo "   Dashboard: http://localhost:5555"

# Open dashboard in browser after a short delay
(sleep 2 && open http://localhost:5555) &

python3 -m flowtrack.main
