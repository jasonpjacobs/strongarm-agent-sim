#!/usr/bin/env python3
"""Actual AI model (Codex or Claude) -> StrongArm trial API -> observations -> model -> replay.

Python validates/routes actions; it does not choose stimulus.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import tempfile
import time

from .config import ROOT as PROJECT_ROOT, load, require
from . import claude_provider
from .client import Simulator
from .replay import replay

ROOT = Path(__file__).resolve().parent
PUBLIC_TRIAL = ('decision', 'status', 'external_diff_V', 'reset_min_V', 'outp_V',
                'outn_V', 'decision_delay_s', 'hold_window_s', 'window_points')

def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False)+'\n')

def journal(path, obj):
    with path.open('a') as stream:
        stream.write(json.dumps(dict(wall_time_utc=datetime.now(timezone.utc).isoformat(), **obj), allow_nan=False)+'\n')
        stream.flush()
        os.fsync(stream.fileno())

def public_observation(observation):
    result = {k: observation[k] for k in ['epoch', 'time_s', 'time_hex', 'state', 'accepted_points']}
    result['trial'] = ({k: observation['trial'][k] for k in PUBLIC_TRIAL}
                       if observation['trial'] is not None else None)
    return result

def finite(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('Expected a finite numeric stimulus or bracket endpoint')
    return float(value)

def validate(proposal, observation, history, remaining_trials, request_id):
    fields = {'action','based_on_epoch','diff_mV','evidence_epochs','explanation',
              'expected_observation','threshold_low_mV','threshold_high_mV'}
    if not isinstance(proposal, dict) or set(proposal) != fields:
        raise ValueError('Response fields do not match schema')
    if type(proposal['based_on_epoch']) is not int or proposal['based_on_epoch'] != observation['epoch']:
        raise ValueError('Proposal references a stale epoch')
    epochs = proposal['evidence_epochs']
    known = {h['result']['epoch'] for h in history}
    if not isinstance(epochs, list) or any(type(e) is not int or e not in known for e in epochs):
        raise ValueError('Evidence must reference observed epochs')
    if observation['epoch'] and observation['epoch'] not in epochs:
        raise ValueError('Include the latest observed epoch in evidence_epochs')
    for field in ['explanation', 'expected_observation']:
        if not isinstance(proposal[field], str) or not 1 <= len(proposal[field].strip()) <= 2500:
            raise ValueError(field+' must be a nonempty concise explanation')
    lo, hi = proposal['threshold_low_mV'], proposal['threshold_high_mV']
    if (lo is None) != (hi is None):
        raise ValueError('Both bracket endpoints must be supplied together')
    if lo is not None:
        lo, hi = finite(lo), finite(hi)
        if lo >= hi:
            raise ValueError('Bracket must be ordered low < high')
        for value, decision in [(lo, 0), (hi, 1)]:
            if not any(h['result']['trial']['decision'] == decision and
                       abs(h['result']['trial']['external_diff_V']*1e3-value) < 1e-9 for h in history):
                raise ValueError('Bracket endpoints must be measured opposite decisions, not predictions')
    if proposal['action'] == 'stop':
        if proposal['diff_mV'] is not None:
            raise ValueError('Stop requires diff_mV=null')
        return None
    if proposal['action'] != 'trial' or remaining_trials <= 0:
        raise ValueError('Unsupported action or trial budget exhausted')
    voltage = finite(proposal['diff_mV'])
    if abs(voltage) > 100:
        raise ValueError('diff_mV must be within [-100,100]')
    # The only stimulus conversion: the model's exact chosen mV value -> volts.
    return dict(method='trial', request_id=request_id,
                based_on_epoch=observation['epoch'], diff_V=voltage*1e-3)

PROVIDERS = {'codex': dict(name='openai-codex-cli', binary='codex_bin',
                            destination='OpenAI through authenticated Codex CLI'),
             'claude': dict(name=claude_provider.PROVIDER, binary='claude_bin',
                            destination='Anthropic through authenticated Claude Code CLI')}

def provider(config):
    name = config.get('provider') or 'codex'
    if name not in PROVIDERS:
        raise ValueError(f'Unsupported provider {name!r}; rerun setup.sh --provider codex|claude')
    return name

def infer(context, folder, model):
    config = load()
    folder.mkdir()
    prompt = (ROOT/'ai_prompt.txt').read_text()+'\nCURRENT CONTEXT:\n'+json.dumps(context, allow_nan=False)
    (folder/'prompt.txt').write_text(prompt)
    shutil.copyfile(ROOT/'ai_decision.schema.json', folder/'schema.json')
    if provider(config) == 'claude':
        return claude_provider.infer((ROOT/'ai_prompt.txt').read_text(), context, folder, model,
                                     require(config, 'claude_bin'), config.get('reasoning_effort', 'high'),
                                     ROOT/'ai_decision.schema.json')
    return infer_codex(prompt, folder, model)

def infer_codex(prompt, folder, model):
    # Separate temporary working directory; no circuit/results are available to
    # the model. Auth remains in Codex's normal credential store and is not read.
    with tempfile.TemporaryDirectory(prefix='strongarm-model-') as temporary:
        work = Path(temporary)
        shutil.copyfile(folder/'schema.json', work/'schema.json')
        command = [require(load(), 'codex_bin'), 'exec', '--ephemeral', '--ignore-user-config',
                   '--sandbox', 'read-only', '--skip-git-repo-check', '--color', 'never',
                   '--model', model, '-c', 'model_reasoning_effort='+json.dumps(load().get('reasoning_effort','high')),
                   '--output-schema', str(work/'schema.json'),
                   '--output-last-message', str(work/'response.json'), '-C', str(work)]
        for feature in ['shell_tool','apps','plugins','multi_agent','hooks','browser_use',
                        'computer_use','code_mode_host','view_image','image_generation',
                        'workspace_dependencies','skill_search']:
            command += ['--disable', feature]
        command += ['-']
        dump(folder/'invocation.json', dict(command=command, provider=PROVIDERS['codex']['name'], requested_model=model))
        start = time.monotonic()
        try:
            with (folder/'stdout.log').open('w') as out, (folder/'stderr.log').open('w') as err:
                subprocess.run(command, input=prompt, text=True, stdout=out, stderr=err, timeout=240, check=True)
        finally:
            dump(folder/'timing.json', dict(inference_wall_seconds=time.monotonic()-start))
        shutil.copyfile(work/'response.json', folder/'response.json')
    runtime = (folder/'stderr.log').read_text()
    found = {k: re.search(rf'(?m)^{k}:\s*(.+)$', runtime) for k in ['model', 'provider']}
    dump(folder/'runtime.json', dict(provider=PROVIDERS['codex']['name'],
         service=found['provider'][1].strip() if found['provider'] else None,
         model=found['model'][1].strip() if found['model'] else None))
    return json.loads((folder/'response.json').read_text())

def accepted_samples(client):
    path = client.folder/'waveforms.jsonl'
    return sum(1 for _ in path.open()) if path.exists() else 0

def verify_replay(base):
    return replay(base/'live', base/'replay')

def evidence_bracket(history):
    """Post-hoc measurement summary only; never used to select an action."""
    negative = [h['result']['trial']['external_diff_V']*1e3 for h in history if h['result']['trial']['decision'] == 0]
    positive = [h['result']['trial']['external_diff_V']*1e3 for h in history if h['result']['trial']['decision'] == 1]
    return [max(negative), min(positive)] if negative and positive else None

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-trials', type=int, default=12)
    parser.add_argument('--max-model-calls', type=int, default=16)
    parser.add_argument('--model', help='Override the model selected during setup')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args(argv)
    config = load()
    args.model = args.model or config.get('model')
    if not args.prepare_only:
        if not args.model:
            parser.error('Select an available model with setup.sh --model or --model')
        from .doctor import check
        check(ai=True,model=args.model)
    if not 3 <= args.max_trials <= 30 or not args.max_trials+1 <= args.max_model_calls <= 40:
        parser.error('Require 3..30 trials and max_trials+1..40 model calls')
    base = (args.output or PROJECT_ROOT/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')).resolve()
    base.mkdir(parents=True, exist_ok=False)
    log = base/'decisions.jsonl'
    selected = PROVIDERS[provider(config)]
    binary = config.get(selected['binary'])
    manifest = dict(provider=selected['name'], requested_model=args.model,
                    reasoning_effort=config.get('reasoning_effort', 'high'),
                    cli_version=subprocess.check_output([binary,'--version'], text=True).strip() if binary else 'not configured',
                    max_trials=args.max_trials, max_model_calls=args.max_model_calls,
                    controller_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    prompt_sha256=hashlib.sha256((ROOT/'ai_prompt.txt').read_bytes()).hexdigest(),
                    schema_sha256=hashlib.sha256((ROOT/'ai_decision.schema.json').read_bytes()).hexdigest(),
                    bootstrap='No scripted trial; model chooses first stimulus at epoch zero',
                    withheld=['injected offset value','core input voltages','prior scripted results',
                              'netlist','PDK files','credentials','unrelated workspace files'])
    dump(base/'agent-manifest.json', manifest)
    print(json.dumps(dict(kind='started', directory=str(base), model=args.model)), flush=True)
    client = Simulator(base/'live')
    history, proposals = [], []
    observation = client.initial
    calls = 0
    stop = None
    try:
        while calls < args.max_model_calls:
            remaining = args.max_trials-len(history)
            context = dict(current=public_observation(observation), history=history,
                           recent_waveform_excerpt=client.excerpt(observation),
                           remaining_trials=remaining,
                           remaining_model_calls_including_this_one=args.max_model_calls-calls,
                           demonstration_target_bracket_mV=.5)
            if args.prepare_only:
                dump(base/'prepared-context.json', context)
                (base/'prepared-prompt.txt').write_text((ROOT/'ai_prompt.txt').read_text()+'\nCURRENT CONTEXT:\n'+json.dumps(context))
                dump(base/'preflight.json', dict(status='PREPARED', model_calls=0,
                     destination=selected['destination'],
                     includes=['circuit description','external stimulus/output measurements','decision history'],
                     excludes=manifest['withheld']))
                print(json.dumps(dict(kind='prepared', directory=str(base), model_calls=0)), flush=True)
                return
            request = None
            for attempt in range(2):
                if calls >= args.max_model_calls:
                    raise RuntimeError('Model call budget exhausted during validation')
                context['remaining_model_calls_including_this_one'] = args.max_model_calls-calls
                calls += 1
                folder = base/f'call-{calls:02d}'
                journal(log, dict(kind='model_input', call=calls, context=context))
                samples_before = accepted_samples(client)
                proposal = infer(context, folder, args.model)
                timing = json.loads((folder/'timing.json').read_text())
                after = client.call(dict(method='observe'))
                samples_after = accepted_samples(client)
                if after != observation or samples_after != samples_before:
                    raise AssertionError('Simulation advanced during model inference')
                journal(log, dict(kind='model_proposal', call=calls, proposal=proposal,
                                  inference=timing, parked_observation_unchanged=True,
                                  waveform_samples_before=samples_before, waveform_samples_after=samples_after,
                                  runtime=json.loads((folder/'runtime.json').read_text()),
                                  before=public_observation(observation), after=public_observation(after)))
                try:
                    request = validate(proposal, observation, history, remaining, f'ai-{len(history)+1:03d}')
                    break
                except ValueError as exc:
                    journal(log, dict(kind='rejected', call=calls, error=str(exc)))
                    context.update(validation_error=str(exc), rejected_proposal=proposal)
                    if attempt:
                        raise
            proposals.append(proposal)
            journal(log, dict(kind='decision_committed', call=calls, proposal=proposal, request=request))
            print(json.dumps(dict(kind='decision', call=calls, proposal=proposal)), flush=True)
            if request is None:
                stop = proposal
                break
            observation = client.call(request)
            item = dict(proposal=proposal, request=request, result=public_observation(observation),
                        inference_wall_seconds=timing['inference_wall_seconds'])
            history.append(item)
            journal(log, dict(kind='experiment_result', call=calls, **item))
            print(json.dumps(dict(kind='observation', call=calls, result=item['result'])), flush=True)
        if stop is None:
            raise RuntimeError('Model-call budget reached without a final stop response')
    except BaseException as exc:
        journal(log, dict(kind='failed', error=str(exc), model_calls=calls))
        raise
    finally:
        client.close()
    if len(history) < 3:
        raise RuntimeError('Too few model-chosen trials to demonstrate adaptive operation')
    replay_result = verify_replay(base)
    runtime_models, model_runtime = [], []
    for folder in sorted(base.glob('call-*')):
        runtime = json.loads((folder/'runtime.json').read_text())
        runtime_models.append(runtime.get('model') or 'see invocation and runtime logs')
        model_runtime.append(dict(call=folder.name, inference_wall_seconds=json.loads(
            (folder/'timing.json').read_text())['inference_wall_seconds'],
            **{k: runtime.get(k) for k in ['provider', 'model', 'duration_ms', 'duration_api_ms',
                                          'num_turns', 'usage', 'total_cost_usd'] if k in runtime}))
    report = dict(status='PASS', provider=manifest['provider'], model_calls=calls, runtime_models=runtime_models,
                  model_runtime=model_runtime,
                  ai_selected_trials=len(history), all_stimuli_selected_by_model=True,
                  parked_during_every_model_call=True, scripted_trial_choices=0,
                  observed_threshold_bracket_mV=evidence_bracket(history),
                  final_model_response=stop, history=history, replay=replay_result,
                  limitations=['Synthetic fixed offset; nominal TT/27 C; no mismatch/noise',
                               'Model chooses differential amplitude; cycle timing is fixed by API',
                               'Replay uses recorded actions, not fresh inference',
                               'Same-environment numerical replay only'])
    dump(base/'verification.json', report)
    from .report import report as make_report
    make_report(base)
    journal(log, dict(kind='replay_verified', **replay_result))
    (PROJECT_ROOT/'.local/latest-run.txt').write_text(str(base)+'\n')
    print(json.dumps(dict(kind='complete', directory=str(base), model_calls=calls,
                          ai_selected_trials=len(history), bracket_mV=evidence_bracket(history), replay=replay_result)), flush=True)

if __name__ == '__main__':
    main()
