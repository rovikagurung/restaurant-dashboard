#!/bin/sh
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 was not found. Install Python 3 first."
  exit 1
fi

python3 -m pip install -r requirements.txt
python3 app.py
