#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1
python3 -m pip install -r requirements.txt
python3 app.py
