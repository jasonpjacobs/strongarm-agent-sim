"""Reapply committed actions, verify provenance and compare accepted history."""
import json
from pathlib import Path
from .client import Simulator

def replay(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    expected = json.loads((source/'manifest.json').read_text())
    events = [json.loads(s) for s in (source/'events.jsonl').read_text().splitlines()]
    client = Simulator(target, expected['series_offset_V'], expected['max_step_s'], expected['reltol'])
    count, last = 0, 0.
    try:
        actual = json.loads((target/'manifest.json').read_text())
        if actual != expected:
            differences = [k for k in set(actual)|set(expected) if actual.get(k) != expected.get(k)]
            raise RuntimeError('Replay provenance differs: '+', '.join(sorted(differences)))
        observations = {e['request_id']:e['observation'] for e in events if e['kind']=='observation'}
        for event in events:
            if event['kind'] == 'trial':
                result = client.call(event['request'])
                if result != observations[event['request']['request_id']]:
                    raise AssertionError('Replay observation differs at '+event['request']['request_id'])
                count += 1
                last = result['time_s']
    finally:
        client.close()
    def samples(folder):
        return [r for s in (folder/'waveforms.jsonl').read_text().splitlines()
                if (r:=json.loads(s))['time'] <= last]
    a,b = samples(source),samples(target)
    if a != b:
        raise AssertionError('Replay accepted times or values differ')
    assert all(x['time'] < y['time'] for x,y in zip(a,a[1:]))
    report = dict(status='PASS', identical_points=len(a), replayed_trials=count,
                  observations_identical=True, environment_identical=True, model_calls=0)
    (target/'replay-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
