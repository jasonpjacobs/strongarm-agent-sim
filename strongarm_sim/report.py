#!/usr/bin/env python3
"""Create an inspectable run viewer and scientific plot from actual AI decisions."""
import argparse
import json
from pathlib import Path
from .audit import audit

ROOT = Path(__file__).resolve().parent

def report(base):
    print(json.dumps(audit(base)))
    data = json.loads((base/'verification.json').read_text())
    template = (ROOT/'viewer.html').read_text()
    encoded = json.dumps(data, allow_nan=False).replace('<', '\\u003c')
    (base/'agent-loop.html').write_text(template.replace('__RUN_DATA__', encoded))
    lines = ['# StrongArm: actual AI-in-the-simulation run', '',
             f"Model: {', '.join(sorted(set(data['runtime_models'])))}. "
             f"{data['model_calls']} model calls; {data['ai_selected_trials']} AI-chosen trials.", '',
             'Every trial uses a separate actual model response. Python validates and routes the chosen amplitude; it contains no next-stimulus policy.', '',
             '| Trial | Model-chosen input (mV) | Observed decision | Model explanation |',
             '| --- | ---: | --- | --- |']
    for i,h in enumerate(data['history'],1):
        lines.append(f"| {i} | {h['proposal']['diff_mV']:.9g} | {h['result']['trial']['decision']} | {h['proposal']['explanation'].replace('|','/')} |")
    lines += ['', 'Model final explanation: '+data['final_model_response']['explanation'], '',
              f"Replay: {data['replay']['identical_points']:,} identical accepted points, all observations identical, zero replay model calls.", '',
              'The fixed offset value, internal input voltages, previous scripted results and netlist were withheld from every model prompt. The model received external stimuli, output observations and its own decision history.', '',
              '[Step through the run](agent-loop.html) · [Provenance audit](provenance-audit.json) · [Decision journal](decisions.jsonl)', '']
    (base/'report.md').write_text('\n'.join(lines))
    try:
        import matplotlib
    except ImportError:
        return dict(status='PASS', report=str(base/'report.md'), viewer=str(base/'agent-loop.html'), plot='optional matplotlib not installed')
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    history = data['history']; x = list(range(1,len(history)+1))
    fig,axes = plt.subplots(2,1,figsize=(11,6.5),sharex=True,gridspec_kw={'height_ratios':[1.4,1]})
    for i,h in enumerate(history,1):
        decision=h['result']['trial']['decision']
        axes[0].scatter(i,h['proposal']['diff_mV'],c='#2269a6' if decision==1 else '#c26b30',s=45,
                        marker='o' if decision==1 else 's')
    axes[0].plot(x,[h['proposal']['diff_mV'] for h in history],c='gray',alpha=.4,lw=1)
    axes[0].set(ylabel='AI-chosen input (mV)',title='Each point comes from a separate model response; blue circles: 1, orange squares: 0')
    axes[1].bar(x,[h['inference_wall_seconds'] for h in history],color='#56778f')
    axes[1].set(ylabel='Model inference time (s)',xlabel='Trial / clock cycle',
                title='Simulation time and sample count stayed unchanged throughout every model call')
    for ax in axes:
        ax.grid(axis='y',alpha=.2)
    axes[1].set_xticks(x)
    fig.suptitle(', '.join(sorted(set(data['runtime_models'])))+' inside the StrongArm simulation\n'+str(data['replay']['identical_points'])+' samples reproduced exactly by action replay')
    fig.tight_layout();fig.savefig(base/'agent-loop.png',dpi=160)

    return dict(status='PASS', report=str(base/'report.md'), viewer=str(base/'agent-loop.html'), plot=str(base/'agent-loop.png'))
