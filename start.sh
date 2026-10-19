#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo 'Uzupełnij .env według README.md, a następnie uruchom ponownie.'
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.lock
exec .venv/bin/python -m botspoti
