#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if [ ! -f "venv/bin/activate" ]; then
    printf 'Ambiente virtual nao encontrado. Execute ./setup.sh primeiro.\n' >&2
    exit 1
fi

. "venv/bin/activate"
python run.py

