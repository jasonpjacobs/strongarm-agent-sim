"""Read-only installation checks; never authenticates or calls a model."""
import ctypes
import importlib.util
from pathlib import Path
import subprocess
import sys
from .config import load, require

def check(ai=False, model=None):
    config = load()
    if sys.version_info < (3,11):
        raise RuntimeError('Python 3.11 or newer is required')
    if sys.platform == 'win32':
        raise RuntimeError('Use a Linux/WSL environment; native Windows is not supported by this pipe transport')
    sky130_lib = Path(require(config, 'sky130_lib'))
    if not sky130_lib.is_file():
        raise RuntimeError(f'SKY130 library not found: {sky130_lib}')
    from .worker import model_hashes
    hashes = model_hashes(sky130_lib)
    library = require(config, 'ngspice_library')
    if not Path(library).is_file():
        raise RuntimeError('ngspice_library must be the full path to libngspice.so/.dylib, not the executable')
    lib = ctypes.CDLL(library)
    for symbol in ['ngSpice_Init','ngSpice_Init_Sync','ngSpice_Command','ngSpice_Circ']:
        if not hasattr(lib,symbol):
            raise RuntimeError(f'Shared ngspice is missing {symbol}')
    executable = require(config,'ngspice_bin')
    version = subprocess.check_output([executable,'--version'],text=True,stderr=subprocess.STDOUT,timeout=15).strip()
    result = dict(status='PASS', python=sys.version.split()[0], ngspice=version,
                  model_include_files=len(hashes), solver=config['solver'],
                  plotting_available=importlib.util.find_spec('matplotlib') is not None,
                  ai_checked=ai)
    if ai and (config.get('provider') or 'codex') == 'claude':
        from .claude_provider import check as claude_check
        result['provider'] = 'anthropic-claude-code-cli'
        result['claude'] = claude_check(require(config,'claude_bin'))
        result['model'] = model or require(config,'model')
        result['effort'] = config.get('reasoning_effort','high')
        result['authentication'] = 'Not tested; use your normal Claude Code login (claude auth login) or ANTHROPIC_API_KEY'
    elif ai:
        codex = require(config,'codex_bin')
        model = model or require(config,'model')
        result['provider'] = 'openai-codex-cli'
        help_text = subprocess.check_output([codex,'exec','--help'],text=True,stderr=subprocess.STDOUT,timeout=15)
        for option in ['--output-schema','--output-last-message','--ephemeral','--ignore-user-config','--disable']:
            if option not in help_text:
                raise RuntimeError(f'Codex lacks {option}; install a CLI compatible with the documented requirements')
        result['codex'] = subprocess.check_output([codex,'--version'],text=True,timeout=15).strip()
        result['model'] = model
        result['authentication'] = 'Not tested; run codex login before an AI run'
    return result
