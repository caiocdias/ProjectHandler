#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

python -m venv venv
. "venv/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

printf '\nAmbiente configurado com sucesso.\n'
printf 'Para iniciar o programa, execute ./ProjectHandler.sh.\n'

