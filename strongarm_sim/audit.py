#!/usr/bin/env python3
"""Independently match actual model responses to every committed solver trial."""
import argparse
import json
from pathlib import Path
import re

def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]

def forbidden_keys(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {'observed_series_offset_V', 'core_input_diff_V', 'series_offset_V', 'netlist'}:
                yield key
            yield from forbidden_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from forbidden_keys(item)

def audit(base):
    base = Path(base)
    log = events(base/'decisions.jsonl')
    inputs = {e['call']:e for e in log if e['kind'] == 'model_input'}
    proposals = {e['call']:e for e in log if e['kind'] == 'model_proposal'}
    commits = [e for e in log if e['kind'] == 'decision_committed']
    actions = [e for e in commits if e['request'] is not None]
    executed = [e['request'] for e in events(base/'live/events.jsonl') if e['kind'] == 'trial']
    assert executed == [e['request'] for e in actions], 'An executed stimulus lacks a model commitment'
    models = set()
    for e in commits:
        call = e['call']
        folder = base/f'call-{call:02d}'
        response = json.loads((folder/'response.json').read_text())
        assert response == e['proposal'] == proposals[call]['proposal']
        runtime = (folder/'stderr.log').read_text()
        model = re.search(r'(?m)^model:\s*(.+)$', runtime)
        provider = re.search(r'(?m)^provider:\s*(.+)$', runtime)
        assert model and provider and provider[1].strip() == 'openai'
        models.add(model[1].strip())
        assert proposals[call]['parked_observation_unchanged']
        assert proposals[call]['before'] == proposals[call]['after']
        assert not list(forbidden_keys(inputs[call]['context'])), 'Withheld data leaked into model context'
        assert inputs[call]['context']['current']['epoch'] == response['based_on_epoch']
        if e['request']:
            assert e['request']['diff_V'] == response['diff_mV']*1e-3
            assert e['request']['based_on_epoch'] == response['based_on_epoch']
            assert e['request']['method'] == 'trial' and response['action'] == 'trial'
        else:
            assert response['action'] == 'stop'
    assert actions[0]['request']['based_on_epoch'] == 0, 'Unexpected scripted bootstrap'
    assert len(actions) >= 3
    assert all(e['proposal']['based_on_epoch'] == i for i,e in enumerate(actions))
    report = json.loads((base/'verification.json').read_text())
    assert report['replay']['status'] == 'PASS' and report['replay']['model_calls'] == 0
    assert report['replay']['replayed_trials'] == len(actions)
    result = dict(status='PASS', runtime_models=sorted(models), independently_matched_trials=len(actions),
                  model_calls=len(inputs), separate_model_response_for_every_trial=True,
                  every_model_wait_preserved_solver_state=True, withheld_context_fields_absent=True,
                  no_scripted_bootstrap_or_fallback=True, replay_model_calls=0)
    (base/'provenance-audit.json').write_text(json.dumps(result, indent=2)+'\n')
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    print(json.dumps(audit(parser.parse_args().directory)))
