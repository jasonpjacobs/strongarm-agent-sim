#!/usr/bin/env python3
"""One continuous transient, parked between cycles; JSON-lines agent API."""
import ctypes as C
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shlex
import sys
import threading

from .fixture import build, canonical
from .config import load, require

D, I, P, B = C.c_double, C.c_int, C.c_void_p, C.c_bool
class Value(C.Structure):
    _fields_ = [('name', C.c_char_p), ('real', D), ('imag', D), ('scale', B), ('complex', B)]
class Values(C.Structure):
    _fields_ = [('count', I), ('index', I), ('values', C.POINTER(C.POINTER(Value)))]
CHAR = C.CFUNCTYPE(I, C.c_char_p, I, P)
EXIT = C.CFUNCTYPE(I, I, B, B, I, P)
DATA = C.CFUNCTYPE(I, C.POINTER(Values), I, I, P)
INIT = C.CFUNCTYPE(I, P, I, P)
BG = C.CFUNCTYPE(I, B, I, P)
SOURCE = C.CFUNCTYPE(I, C.POINTER(D), D, C.c_char_p, I, P)
SYNC = C.CFUNCTYPE(I, D, C.POINTER(D), D, I, I, I, P)
ROOT = Path(__file__).resolve().parent
PERIOD = 20e-9

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def model_hashes(path, found=None):
    """Hash the recursive include closure, including every library section."""
    found = {} if found is None else found
    path = Path(path).resolve()
    if str(path) in found:
        return found
    found[str(path)] = digest(path)
    for line in path.read_text().splitlines():
        if line.lstrip().lower().startswith(('.include ', '.inc ', '.lib ')):
            fields = shlex.split(line)
            if fields[0].lower() == '.lib' and len(fields) < 3:
                continue
            child = Path(fields[1])
            model_hashes(child if child.is_absolute() else path.parent/child, found)
    return found

def classify(rows, start, differential):
    """Use sustained output rails, never the known injected offset, to decide."""
    window = lambda lo, hi: [r for r in rows if start+lo <= r['time'] <= start+hi]
    reset = window(8e-9, 9e-9)
    before = window(9.5e-9, 10e-9)
    hold = window(13e-9, 19e-9)
    phase = window(10.05e-9, 19e-9)
    if min(map(len, [reset, before, hold, phase])) < 5:
        raise RuntimeError('Missing samples in a measurement window')
    reset_min = min(r[n] for r in reset for n in ['outp', 'outn', 'xdut.n_inp', 'xdut.n_inn'])
    if reset_min < 1.71 or any(r['clk'] > .18 for r in reset):
        raise RuntimeError('Precharge failed; cannot update the bracket')
    if any(abs(r['inp_ext']-r['inn']-differential) > 1e-7 or
           abs((r['inp_ext']+r['inn'])/2-.9) > 1e-7 for r in before):
        raise RuntimeError('Applied stimulus differs from committed stimulus')
    if any(r['clk'] < 1.62 for r in hold):
        raise RuntimeError('Clock is not high in decision window')
    positive = lambda r: r['outp'] >= 1.62 and r['outn'] <= .18
    negative = lambda r: r['outn'] >= 1.62 and r['outp'] <= .18
    decision = 1 if all(map(positive, hold)) else 0 if all(map(negative, hold)) else None
    delay = None
    if decision is not None:
        valid = positive if decision else negative
        last_bad = max((i for i, r in enumerate(phase) if not valid(r)), default=-1)
        if last_bad+1 < len(phase):
            delay = phase[last_bad+1]['time']-(start+10.05e-9)
    return dict(decision=decision, status='resolved' if decision is not None else 'unresolved',
                external_diff_V=differential, reset_min_V=reset_min,
                outp_V=hold[-1]['outp'], outn_V=hold[-1]['outn'],
                observed_series_offset_V=before[-1]['inp']-before[-1]['inp_ext'],
                core_input_diff_V=before[-1]['inp']-before[-1]['inn'],
                decision_delay_s=delay, hold_window_s=[start+13e-9, start+19e-9],
                window_points=len(hold))

class Engine:
    def __init__(self, directory, offset=.043, max_step=5e-12, reltol=1e-5):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.log = (self.directory/'events.jsonl').open('w')
        self.wave = (self.directory/'waveforms.jsonl').open('w')
        self.messages = (self.directory/'ngspice.log').open('w')
        self.cv = threading.Condition()
        self.parked = self.done = self.closing = False
        self.now = self.target = 0.
        self.epoch = 0
        self.rows, self.ramps = [], []
        self.cache = {}
        self.last = None
        self.retries = 0
        config = load()
        libpath = require(config, 'ngspice_library')
        self.lib = C.CDLL(libpath)
        self.callbacks = [CHAR(self.message), CHAR(lambda *a: 0), EXIT(self.exited),
                          DATA(self.data), INIT(lambda *a: 0), BG(self.background)]
        self.sources = [SOURCE(self.voltage), SOURCE(lambda *a: 0), SYNC(self.sync)]
        self.lib.ngSpice_Init.argtypes = [CHAR, CHAR, EXIT, DATA, INIT, BG, P]
        self.lib.ngSpice_Init_Sync.argtypes = [SOURCE, SOURCE, SYNC, C.POINTER(I), P]
        self.lib.ngSpice_Command.argtypes = [C.c_char_p]
        self.lib.ngSpice_Circ.argtypes = [C.POINTER(C.c_char_p)]
        empty = self.directory/'empty-init'
        empty.mkdir()
        os.environ['SPICE_SCRIPTS'] = os.environ['SPICE_USERINIT_DIR'] = str(empty.resolve())
        self.lib.ngSpice_Init(*self.callbacks, None)
        self.ident = I(0)
        self.lib.ngSpice_Init_Sync(*self.sources, C.byref(self.ident), None)
        for command in ['set ngbehavior=hsa', 'set num_threads=1']:
            self.command(command)
        circuit = self.directory/'circuit.cir'
        circuit.write_text(build(offset, max_step, reltol))
        model = Path(require(config, 'sky130_lib'))
        absolute_hashes = model_hashes(model)
        hashes = {os.path.relpath(p, model.resolve().parent): h for p,h in absolute_hashes.items()}
        (self.directory/'model-hashes.json').write_text(json.dumps(hashes, sort_keys=True, indent=2))
        manifest = dict(schema=2, netlist_sha256=hashlib.sha256(canonical(circuit.read_text()).encode()).hexdigest(), library_sha256=digest(libpath),
                        worker_sha256=digest(__file__), fixture_builder_sha256=digest(ROOT/'fixture.py'),
                        config_code_sha256=digest(ROOT/'config.py'),
                        solver=config['solver'],
                        model_tree_sha256=hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
                        platform=platform.platform(), python=platform.python_version(), threads=1,
                        series_offset_V=offset, max_step_s=max_step, reltol=reltol,
                        period_s=PERIOD, corner='tt', temperature_C=27,
                        input_transition='100 ps cubic smoothstep, starting 2 ns into reset',
                        initialization='isolated empty SPICE_SCRIPTS / SPICE_USERINIT_DIR')
        (self.directory/'manifest.json').write_text(json.dumps(manifest, indent=2))
        # Pass lines through the shared-library API. The interactive `source`
        # command does not reliably strip quotes from paths containing spaces.
        self.netlist_lines = [line.encode() for line in circuit.read_text().splitlines()]
        self.netlist_array = (C.c_char_p*(len(self.netlist_lines)+1))(*self.netlist_lines, None)
        if self.lib.ngSpice_Circ(self.netlist_array) != 0:
            raise RuntimeError('ngSpice_Circ failed; inspect ngspice.log')
        if config['solver'] == 'klu':
            self.command('option klu')
        self.command('bg_run')
        self.wait()
        self.record(dict(kind='created', observation=self.observe()))

    def command(self, command):
        result = self.lib.ngSpice_Command(command.encode())
        if result != 0:
            raise RuntimeError(f'ngspice command failed ({result}): {command}')

    def record(self, event):
        self.log.write(json.dumps(event, allow_nan=False)+'\n')
        self.log.flush()
        os.fsync(self.log.fileno())

    def message(self, value, *_):
        if not self.messages.closed:
            self.messages.write(value.decode(errors='replace')+'\n')
            self.messages.flush()
        return 0

    def exited(self, *_):
        with self.cv:
            self.done = True
            self.cv.notify_all()
        return 0

    def background(self, inactive, *_):
        if inactive:
            self.exited()
        return 0

    def differential(self, t):
        value = 0.
        for start, end, initial, final in self.ramps:
            if t < start:
                break
            if t < end:
                x = (t-start)/(end-start)
                return initial+(final-initial)*(3*x*x-2*x*x*x)
            value = final
        return value

    def voltage(self, result, t, name, *_):
        source = name.decode().lower()
        result[0] = .9 + (1 if source == 'vinp' else -1)*self.differential(t)/2
        return 0

    def data(self, values, *_):
        if self.closing:
            return 0
        v = values.contents
        row = {v.values[k].contents.name.decode(): v.values[k].contents.real for k in range(v.count)}
        if 'time' in row:
            self.rows.append(row)
            self.wave.write(json.dumps(row, allow_nan=False)+'\n')
        return 0

    def sync(self, t, delta, olddelta, redo, ident, loc, user):
        self.retries += bool(redo)
        if loc == 0:
            with self.cv:
                self.now = t
                if not self.closing and t >= self.target-1e-18:
                    self.parked = True
                    self.wave.flush()
                    self.cv.notify_all()
                    while self.parked and not self.closing:
                        self.cv.wait()
        if not self.closing:
            boundaries = [self.target]
            for start, end, _, _ in self.ramps:
                boundaries.extend([start, end])
                if start-1e-18 <= t < end:
                    delta[0] = min(delta[0], (end-start)/20)
            future = [b for b in boundaries if b > t+1e-18]
            if future:
                delta[0] = min(delta[0], min(future)-t)
        return 0

    def wait(self):
        with self.cv:
            if not self.cv.wait_for(lambda: self.parked or self.done, timeout=60):
                raise TimeoutError('Simulator did not reach a barrier within 60 seconds')
            if self.done and not self.parked:
                raise RuntimeError('Simulation ended before the barrier; inspect ngspice.log')

    def observe(self):
        return dict(epoch=self.epoch, time_s=self.now, time_hex=self.now.hex(),
                    state='parked' if self.parked else 'running', accepted_points=len(self.rows),
                    retry_callbacks=self.retries, trial=self.last)

    def trial(self, req):
        key = req['request_id']
        if not isinstance(key, str) or not key:
            raise ValueError('request_id must be a nonempty string')
        encoded = json.dumps(req, sort_keys=True, allow_nan=False)
        if key in self.cache:
            previous, response = self.cache[key]
            if previous != encoded:
                raise ValueError('request_id reused with different contents')
            return response
        if not self.parked or req['based_on_epoch'] != self.epoch:
            raise ValueError('stale epoch or simulator not parked')
        differential = float(req['diff_V'])
        if not math.isfinite(differential) or abs(differential) > .2:
            raise ValueError('diff_V must be finite and within +/-0.2 V')
        if self.epoch >= 90:
            raise ValueError('90-cycle limit reached')
        start = self.epoch*PERIOD
        ramp = [start+2e-9, start+2.1e-9, self.differential(start), differential]
        self.record(dict(kind='trial', request=req, committed_ramp=ramp, from_time_hex=self.now.hex()))
        index = len(self.rows)
        with self.cv:
            self.ramps.append(ramp)
            self.epoch += 1
            self.target = self.epoch*PERIOD
            self.parked = False
            self.cv.notify_all()
        self.wait()
        self.last = classify(self.rows[index:], start, differential)
        response = self.observe()
        self.record(dict(kind='observation', request_id=key, observation=response))
        self.cache[key] = (encoded, response)
        return response

    def close(self):
        with self.cv:
            self.closing = True
            self.parked = False
            self.cv.notify_all()
        self.command('bg_halt')
        self.record(dict(kind='closed'))
        for stream in [self.log, self.wave, self.messages]:
            stream.close()

def main():
    engine = None
    try:
        engine = Engine(sys.argv[1], *map(float, sys.argv[2:]))
        print(json.dumps(dict(ok=True, result=engine.observe())), flush=True)
        for line in sys.stdin:
            try:
                req = json.loads(line)
                if req['method'] == 'close':
                    break
                if req['method'] == 'observe':
                    result = engine.observe()
                elif req['method'] == 'trial':
                    result = engine.trial(req)
                else:
                    raise ValueError('Supported methods: observe, trial, close')
                print(json.dumps(dict(ok=True, result=result), allow_nan=False), flush=True)
            except Exception as exc:
                print(json.dumps(dict(ok=False, error=str(exc))), flush=True)
    finally:
        if engine:
            engine.close()

if __name__ == '__main__':
    main()
