"""Single-park destinations; existing environment names remain supported."""
import json
import os
from pathlib import Path
import re
import tempfile

ROUTE_KEYS = {'DRIVER_GROUP_1', 'DRIVER_GROUP_2', 'BRAND_GROUP', 'SPECTRE_GROUP',
              'CHALA_RASM_GROUP', 'OTHER_PARK_GROUP', 'ARCHIVE_GROUP'}


def settings_path():
    return Path(os.environ.get('PERSIST_DIR') or Path(__file__).resolve().parents[1]) / 'bot_routes.json'


def read_settings():
    path = settings_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError('Invalid routes file')
    return {key: validate(key, value) for key, value in data.items()}


def validate(key, value):
    if key not in ROUTE_KEYS or not isinstance(value, str) or not re.fullmatch(r'-[1-9][0-9]*', value.strip()):
        raise ValueError('Invalid route: ' + str(key))
    return value.strip()


def destination(key, fallback=''):
    data = read_settings()
    return data[key] if key in data else os.environ.get(key, fallback).strip()


def save_settings(updates):
    data = read_settings()
    data.update({key: validate(key, value) for key, value in updates.items()})
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.routes-')
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(data, handle, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
