#!/bin/bash
if [ -d ".venv" ] && [ -z "$VIRTUAL_ENV" ]; then
    source .venv/bin/activate
fi
uvicorn src.app:app --reload --port 8000