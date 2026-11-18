#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -d venv ] || { python3 -m venv venv; . venv/bin/activate; pip install -r requirements.txt; }
[ -f venv/Scripts/activate ] && . venv/Scripts/activate || . venv/bin/activate
[ -f .env ] || cp .env.example .env
python app.py
