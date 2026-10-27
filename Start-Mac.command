#!/bin/bash
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "First run: setting up the app, this takes a minute or two..."
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python not found. Install it from https://www.python.org/downloads/ and run this again."
    read -p "Press Enter to close."; exit 1
  fi
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip -q
  .venv/bin/python -m pip install -r requirements.txt -q
fi
echo "Opening the Day Trader Panel in your browser. To quit, press Ctrl+C or close this window."
.venv/bin/python -m streamlit run app.py --browser.gatherUsageStats false
