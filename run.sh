#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
[ -d venv ] || python -m venv venv || python3 -m venv venv
if [ -f venv/Scripts/activate ]; then . venv/Scripts/activate; else . venv/bin/activate; fi
python -m pip install --upgrade pip -q
pip install -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "*** .env created - fill in your Kotak details ***"; }
python app.py
