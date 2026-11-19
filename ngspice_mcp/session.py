"""Serialized worker transport and exact replay, independent of an MCP host."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading

from .data import write_json

ROOT = Path(__file__).resolve().parent.parent


class Session:
    def __init__(self, directory, library, spec):
        self.directory = Path(directory).resolve()
        self.library = str(Path(library).resolve())
        self.lock = threading.RLock()
        self.closed = False
        self.final = None
        self.directory.mkdir(parents=True, exist_ok=False)
        write_json(self.directory/'spec.json', spec)
        self.stderr = (self.directory/'worker-stderr.log').open('w')
        env = dict(os.environ)
        env['PYTHONPATH'] = str(ROOT)+os.pathsep+env.get('PYTHONPATH','')
        self.process = subprocess.Popen([sys.executable,'-m','ngspice_mcp.worker',str(self.directory),self.library],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                                        text=True, env=env, cwd=ROOT)
        try:
            self.initial = self._read()
        except BaseException:
            self._terminate()
            raise

    def _read(self):
        if not select.select([self.process.stdout], [], [], 75)[0]:
            self._terminate()
            raise TimeoutError('Worker timed out; process terminated; inspect run logs')
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('Worker exited; inspect worker-stderr.log and ngspice.log')
        response = json.loads(line)
        if not response['ok']:
            raise ValueError(response['error'])
        return response['result']

    def call(self, request):
        with self.lock:
            if self.closed:
                raise ValueError('Session is closed')
            self.process.stdin.write(json.dumps(request, allow_nan=False)+'\n')
            self.process.stdin.flush()
            return self._read()

    def _terminate(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for stream in [self.process.stdin, self.process.stdout, self.stderr]:
            stream.close()
        self.closed = True

    def close(self):
        with self.lock:
            if self.closed:
                return self.final
            try:
                self.final = self.call({'method':'close'})
                self.process.wait(timeout=10)
                write_json(self.directory/'closed.json', self.final)
                return self.final
            finally:
                self._terminate()


def replay(source, target, library):
    source = Path(source).resolve()
    final = json.loads((source/'closed.json').read_text())
    if final['state'] != 'parked' or final['failure']:
        raise ValueError('Only healthy, explicitly closed sessions can be replayed')
    events = [json.loads(line) for line in (source/'events.jsonl').read_text().splitlines()]
    requests = [e['request'] for e in events if e['kind']=='committed']
    observations = {e['request_id']:e['observation'] for e in events if e['kind']=='result'}
    if len(observations) != len(requests):
        raise ValueError('Incomplete commitment; cannot claim exact replay')
    baseline = json.loads((source/'manifest.json').read_text())
    worker = Session(target, library, json.loads((source/'spec.json').read_text()))
    try:
        actual = json.loads((worker.directory/'manifest.json').read_text())
        if actual != baseline:
            changed = sorted(k for k in baseline.keys()|actual.keys() if baseline.get(k)!=actual.get(k))
            raise ValueError('Replay provenance differs: '+', '.join(changed))
        initial = next(e['observation'] for e in events if e['kind']=='created')
        if worker.initial['observation'] != initial:
            raise AssertionError('Initial observation differs')
        for request in requests:
            if worker.call(request) != observations[request['request_id']]:
                raise AssertionError('Observation differs at '+request['request_id'])
    finally:
        worker.close()
    def rows(folder):
        return [row for line in (folder/'waveforms.jsonl').read_text().splitlines()
                if (row:=json.loads(line))['time'] <= final['time_s']]
    before, after = rows(source), rows(worker.directory)
    if before != after:
        raise AssertionError('Accepted waveform samples differ')
    if worker.final != final:
        raise AssertionError('Final observation differs')
    result = dict(status='PASS', replayed_actions=len(requests),
                  replayed_advances=sum(r['method']=='advance' for r in requests),
                  identical_points=len(before), observations_identical=True,
                  environment_identical=True, model_calls=0)
    write_json(worker.directory/'replay-verification.json', result)
    return result
