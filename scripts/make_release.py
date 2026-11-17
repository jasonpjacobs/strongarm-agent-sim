#!/usr/bin/env python3
"""Create archives from tracked, committed source only; never include local runs."""
import hashlib
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent.parent

def main():
    status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    if status.strip():
        raise SystemExit('Commit source changes first. Release archives use HEAD; local config/runs are ignored.')
    output=ROOT/'dist';output.mkdir(exist_ok=True)
    name='strongarm-agent-sim-0.1.0'
    checks=[]
    for extension,kind in [('tar.gz','tar.gz'),('zip','zip')]:
        path=output/(name+'.'+extension)
        subprocess.run(['git','archive','--format='+kind,'--prefix='+name+'/', '-o',str(path),'HEAD'],cwd=ROOT,check=True)
        checks.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
        print(path)
    (output/'SHA256SUMS').write_text('\n'.join(checks)+'\n')

if __name__=='__main__':main()
