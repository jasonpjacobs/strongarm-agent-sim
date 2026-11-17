"""Local, ignored tool configuration. No credentials are stored here."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load():
    path = Path(os.environ.get('STRONGARM_CONFIG', ROOT/'.local/config.json')).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f'Configuration missing: {path}. Run ./setup.sh --help first.')
    data = json.loads(path.read_text())
    if data.get('schema') != 1:
        raise ValueError('Unsupported configuration schema; rerun setup.sh')
    return data

def require(config, key):
    if not config.get(key):
        raise RuntimeError(f'{key} is not configured; rerun ./setup.sh with the corresponding option')
    return config[key]
