"""Small CLI; live AI and recorded replay are distinct commands."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from .config import ROOT, load, require

def main():
    parser=argparse.ArgumentParser(description='StrongArm agent-in-the-simulation experiment')
    sub=parser.add_subparsers(dest='command',required=True)
    doctor=sub.add_parser('doctor',help='Check paths, models and shared-library ABI; no model calls')
    doctor.add_argument('--ai',action='store_true')
    sub.add_parser('ai',help='Run actual model-selected experiments and replay',add_help=False)
    smoke=sub.add_parser('smoke',help='Scripted basic-operation and synchronization tests; no model calls')
    smoke.add_argument('--output',type=Path)
    recorded=sub.add_parser('recorded',help='Recreate recorded AI actions, then exact local replay; no model calls')
    recorded.add_argument('--source',type=Path);recorded.add_argument('--output',type=Path)
    replay=sub.add_parser('replay',help='Replay saved worker events into a new directory; no model calls')
    replay.add_argument('source',type=Path);replay.add_argument('--output',type=Path,required=True)
    report=sub.add_parser('report',help='Generate a local report/viewer from a completed AI run')
    report.add_argument('directory',type=Path)
    audit=sub.add_parser('audit',help='Match model responses to every simulator action')
    audit.add_argument('directory',type=Path)
    sub.add_parser('schematic',help='Open the optional Xschem core schematic')
    args,rest=parser.parse_known_args()
    if args.command!='ai' and rest: parser.error('Unknown arguments: '+' '.join(rest))
    if args.command=='ai':
        from .agent import main as agent
        return agent(rest)
    if args.command=='doctor':
        from .doctor import check
        result=check(args.ai)
    elif args.command=='smoke':
        from .experiments import smoke
        result=smoke(args.output)
    elif args.command=='recorded':
        from .experiments import recorded
        result=recorded(args.source,args.output)
    elif args.command=='replay':
        from .replay import replay
        result=replay(args.source,args.output)
    elif args.command=='report':
        from .report import report
        result=report(args.directory.resolve())
    elif args.command=='audit':
        from .audit import audit
        result=audit(args.directory.resolve())
    else:
        config=load()
        import os
        env=dict(os.environ,SKY130_XSCHEM_RC=require(config,'sky130_xschem_rc'))
        subprocess.run([require(config,'xschem_bin'),'--rcfile',str(ROOT/'schematics/xschemrc'),str(ROOT/'schematics/strongarm.sch')],env=env,check=True)
        return
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try: main()
    except (RuntimeError,ValueError,OSError,subprocess.SubprocessError) as exc:
        print('Error: '+str(exc),file=sys.stderr)
        raise SystemExit(1)
