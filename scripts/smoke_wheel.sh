#!/usr/bin/env bash
# Сборка wheel → чистый venv → lib работает (ассет токенизатора в пакете).
set -euo pipefail
cd "$(dirname "$0")/.."
uv build --wheel
VENV_ROOT=$(mktemp -d)
TMP=$(mktemp -d)
trap 'rm -rf "$VENV_ROOT" "$TMP"' EXIT
VENV="$VENV_ROOT/venv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet dist/librarian_cli-*.whl
printf 'Глава 1\n\nПроверка установки из колеса, текст главы номер один достаточной длины.\n\nГлава 2\n\nВторая глава смоук-теста установки тоже не совсем пустая.\n' > "$TMP/книга.txt"
SOURCE_DATE_EPOCH=0 "$VENV/bin/lib" --library "$TMP/lib" ingest "$TMP/книга.txt"
"$VENV/bin/lib" --library "$TMP/lib" get "$("$VENV/bin/python" -c "
import json,sys; print(json.load(open('$TMP/lib/index.json'))['books'][0]['id'])")" 1
"$VENV/bin/librarian-cli" --help >/dev/null
echo "SMOKE OK"
