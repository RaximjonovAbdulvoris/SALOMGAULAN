#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo 'VPSda root sifatida ishga tushiring.' >&2
  exit 1
fi

app_dir=/root/SALOMGAULAN
repo=https://github.com/RaximjonovAbdulvoris/SALOMGAULAN.git
if [[ ! -d "$app_dir/.git" ]]; then
  git clone "$repo" "$app_dir"
else
  if [[ -n $(git -C "$app_dir" status --porcelain) ]]; then
    echo 'Repo ichida mahalliy o‘zgarishlar bor; avval tekshiring.' >&2
    exit 1
  fi
  git -C "$app_dir" pull --ff-only
fi
cd "$app_dir"
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt -r requirements-ocr.txt
mkdir -p runtime
chmod 700 runtime

if [[ ! -f .env ]]; then
  venv/bin/python - <<'PY'
from getpass import getpass
from pathlib import Path
import os
import re
import tempfile

token = getpass('SALOM bot tokenini kiriting (ekranda ko‘rinmaydi): ').strip()
if not re.fullmatch(r'[0-9]{7,12}:[A-Za-z0-9_-]{25,}', token):
    raise SystemExit('Token formati noto‘g‘ri; fayl saqlanmadi.')
template = Path('.env.example').read_text()
text = template.replace('TELEGRAM_BOT_TOKEN=\n', f'TELEGRAM_BOT_TOKEN={token}\n', 1)
text = text.replace('PERSIST_DIR=./runtime', 'PERSIST_DIR=/root/SALOMGAULAN/runtime')
fd, name = tempfile.mkstemp(prefix='.salom-env-', dir='.')
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
    os.replace(name, '.env')
finally:
    Path(name).unlink(missing_ok=True)
print('Maxfiy sozlama saqlandi.')
PY
fi
chmod 600 .env
set -a
source .env
set +a

venv/bin/python -m compileall -q bot
venv/bin/python -m bot.configure check --offline
venv/bin/python scripts/check_neural_ocr.py
venv/bin/python -m bot.configure check

cat >/etc/systemd/system/salomgaulan.service <<'UNIT'
[Unit]
Description=WB SALOM Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/SALOMGAULAN
EnvironmentFile=/root/SALOMGAULAN/.env
ExecStart=/root/SALOMGAULAN/venv/bin/python -m bot.main
Restart=always
RestartSec=10
TimeoutStopSec=90
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable salomgaulan
systemctl restart salomgaulan
systemctl is-active salomgaulan
echo 'SALOM bot ishga tushdi; haqiqiy ariza bilan yakuniy sinov kerak.'
