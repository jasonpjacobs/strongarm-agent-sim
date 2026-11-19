#!/usr/bin/env python3
"""Configure the general MCP server independently of SKY130 and model clients."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

from setup_env import discover_library, discover_model

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice-library', help='Path to libngspice.so or libngspice.dylib')
    parser.add_argument('--sky130-lib', help='Optional SKY130 model path for the StrongArm test fixture')
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error('Python 3.11+ required; select it with PYTHON_BIN=/path/to/python3')
    library = discover_library(args.ngspice_library)
    if not library:
        parser.error('Supply --ngspice-library /path/to/libngspice.so (or .dylib); a CLI alone is insufficient')
    lib = ctypes.CDLL(library)
    for symbol in ('ngSpice_Init', 'ngSpice_Init_Sync', 'ngSpice_Command', 'ngSpice_Circ'):
        if not hasattr(lib, symbol):
            parser.error('Shared library is missing '+symbol)
    model = discover_model(args.sky130_lib)
    if args.sky130_lib and not model:
        parser.error('The supplied SKY130 library does not exist')
    # An EDA login environment can inject unrelated Python packages into a venv.
    env = {k:v for k,v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    venv = ROOT/'.venv-mcp'
    subprocess.run([sys.executable, '-m', 'venv', str(venv)], env=env, check=True)
    python = str(venv/'bin/python')
    subprocess.run([python, '-m', 'pip', 'install', '-r', str(ROOT/'requirements-mcp.txt')], env=env, check=True)
    subprocess.run([python, '-c', 'from mcp.server import MCPServer; from ngspice_mcp.server import make_server'],
                   cwd=ROOT, env=env, check=True)
    config = dict(schema=1, ngspice_library=library, python_bin=python, sky130_lib=model)
    local = ROOT/'.local'; local.mkdir(exist_ok=True)
    path = local/'mcp-config.json'
    candidate = path.with_suffix('.candidate')
    candidate.write_text(json.dumps(config, indent=2)+'\n')
    candidate.replace(path)
    print(f'Configured {path}\nMCP launcher: {ROOT / "mcp.sh"}')
    print('The RC example is ready. SKY130 is only needed for the StrongArm fixture.')
    print('No model client is installed or called. Configure your MCP host to launch mcp.sh over stdio.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit('MCP setup failed: '+str(exc))
