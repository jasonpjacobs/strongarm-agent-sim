#!/usr/bin/env python3
"""Discover/configure tools without modifying system or shell startup files."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

def executable(value, name, required=True):
    found = shutil.which(value or name)
    if not found and value and Path(value).is_file() and os.access(value,os.X_OK):
        found = str(Path(value).expanduser().absolute())
    if required and not found:
        raise ValueError(f'{name} not found. Install it, or supply --{name.replace("_", "-")} /absolute/path.')
    return str(Path(found).absolute()) if found else None

def discover_model(value):
    candidates = [value, os.environ.get('SKY130_MODEL_LIB')]
    if os.environ.get('PDK_ROOT'):
        base = Path(os.environ['PDK_ROOT']).expanduser()
        candidates += [base/'sky130A/libs.tech/ngspice/sky130.lib.spice', base/'libs.tech/ngspice/sky130.lib.spice']
    return next((str(Path(p).expanduser().resolve()) for p in candidates if p and Path(p).expanduser().is_file()), None)

def discover_library(value):
    if value or os.environ.get('NGSPICE_LIBRARY'):
        p = Path(value or os.environ['NGSPICE_LIBRARY']).expanduser().resolve()
        return str(p) if p.is_file() else None
    for pattern in ['/usr/lib/*/libngspice.so*','/usr/lib/libngspice.so*','/usr/local/lib/libngspice.*',
                    '/opt/homebrew/lib/libngspice.*','/opt/local/lib/libngspice.*']:
        import glob
        candidates = sorted(glob.glob(pattern))
        if candidates:
            return str(Path(candidates[0]).resolve())
    return None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sky130-lib', help='Full path to installed sky130.lib.spice (ngspice-compatible open_pdks build)')
    parser.add_argument('--ngspice', help='ngspice CLI executable; otherwise search PATH')
    parser.add_argument('--ngspice-library', help='Full path to libngspice.so or libngspice.dylib')
    parser.add_argument('--codex', help='Optional Codex CLI executable; otherwise search PATH')
    parser.add_argument('--model', help='A model available to your Codex account; required only for live AI')
    parser.add_argument('--xschem', help='Optional Xschem executable')
    parser.add_argument('--solver', choices=['sparse','klu'], default='sparse', help='Use klu only when supported by your ngspice build')
    parser.add_argument('--with-plots', action='store_true', help='Create .venv and install optional plot dependencies from PyPI')
    parser.add_argument('--config', type=Path, default=ROOT/'.local/config.json')
    args = parser.parse_args()
    if sys.version_info < (3,11):
        parser.error('Python 3.11+ required; choose it with PYTHON_BIN=/path/to/python3 ./setup.sh ...')
    model = discover_model(args.sky130_lib)
    library = discover_library(args.ngspice_library)
    if not model:
        parser.error('SKY130 library not found. Supply --sky130-lib /path/to/sky130A/libs.tech/ngspice/sky130.lib.spice')
    if not library:
        parser.error('Shared ngspice not found. Supply --ngspice-library /full/path/to/libngspice.so (or .dylib)')
    if any(c in model for c in ['"','\n','\r']):
        parser.error('SKY130 path cannot contain quotes or newlines')
    python = sys.executable
    if args.with_plots:
        venv = ROOT/'.venv'
        subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
        python = str(venv/'bin/python')
        subprocess.run([python,'-m','pip','install','-r',str(ROOT/'requirements-plot.txt')],check=True)
    config = dict(schema=1, sky130_lib=model, ngspice_library=library,
                  ngspice_bin=executable(args.ngspice,'ngspice'), python_bin=python,
                  codex_bin=executable(args.codex,'codex',False), model=args.model,
                  xschem_bin=executable(args.xschem,'xschem',False),
                  solver=args.solver, reasoning_effort='high')
    if args.codex and not config['codex_bin']:
        parser.error('The supplied --codex executable was not found')
    if args.xschem and not config['xschem_bin']:
        parser.error('The supplied --xschem executable was not found')
    xschem_rc = Path(model).parent.parent/'xschem/xschemrc'
    config['sky130_xschem_rc'] = str(xschem_rc) if xschem_rc.is_file() else None
    path = args.config.expanduser().resolve()
    path.parent.mkdir(parents=True,exist_ok=True)
    # Validate the candidate before replacing an existing working configuration.
    candidate = path.with_name(path.name+'.candidate')
    candidate.write_text(json.dumps(config,indent=2)+'\n')
    old_env = os.environ.get('STRONGARM_CONFIG')
    os.environ['STRONGARM_CONFIG'] = str(candidate)
    try:
        from strongarm_sim.doctor import check
        result = check()
    finally:
        if old_env is not None: os.environ['STRONGARM_CONFIG'] = old_env
        else: os.environ.pop('STRONGARM_CONFIG',None)
    candidate.replace(path)
    local = ROOT/'.local';local.mkdir(exist_ok=True)
    variables = dict(STRONGARM_CONFIG=str(path), STRONGARM_PYTHON=python, SKY130_MODEL_LIB=model,
                     NGSPICE_BIN=config['ngspice_bin'], NGSPICE_LIBRARY=library,
                     CODEX_BIN=config['codex_bin'], XSCHEM_BIN=config['xschem_bin'],
                     SKY130_XSCHEM_RC=config['sky130_xschem_rc'])
    lines = ['# Generated by setup.sh; local paths only, no credentials.']
    lines += [f'export {k}={shlex.quote(v)}' for k,v in variables.items() if v]
    directories = list(dict.fromkeys(str(Path(v).parent) for v in [python,config['ngspice_bin'],config['codex_bin'],config['xschem_bin']] if v))
    lines.append('export PATH='+shlex.quote(':'.join(directories))+':"$PATH"')
    (local/'env.sh').write_text('\n'.join(lines)+'\n')
    (local/'setup-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Configured {path}\nLocal environment: {local/"env.sh"}\nNext: ./run.sh doctor && ./run.sh smoke')
    if not config['model'] or not config['codex_bin']:
        print('Recorded runs and replay are ready. Live AI additionally needs Codex login and --model during setup.')

if __name__ == '__main__':
    try:
        main()
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as exc:
        raise SystemExit('Setup failed: '+str(exc))
