"""One shared-ngspice instance per process. No circuit-specific timing or metrics."""
import ctypes as C
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import threading

from .abi import CHAR, EXIT, DATA, INIT, BG, SOURCE, SYNC, I
from .data import Schedule, digest, finite, include_files, signal_name, time_tolerance, unit, waveform, write_json


class Engine:
    def __init__(self, directory, library):
        self.directory = Path(directory).resolve()
        self.spec = json.loads((self.directory/'spec.json').read_text())
        self.cv = threading.Condition()
        self.parked = self.done = self.closing = False
        self.failure = None
        self.now = self.target = 0.0
        self.epoch = 0
        self.rows, self.signals, self.cache = [], [], {}
        self.schedule = Schedule(self.spec['controls'])
        self.log = (self.directory/'events.jsonl').open('w')
        self.wave = (self.directory/'waveforms.jsonl').open('w')
        self.messages = (self.directory/'ngspice.log').open('w')
        empty = self.directory/'empty-init'
        empty.mkdir()
        os.environ['SPICE_SCRIPTS'] = os.environ['SPICE_USERINIT_DIR'] = str(empty)
        os.chdir(self.spec['circuit_directory'])
        includes = include_files(self.spec['deck'], Path.cwd())
        write_json(self.directory/'model-hashes.json', includes)
        code = {name: digest(Path(__file__).with_name(name)) for name in ('worker.py','abi.py','data.py')}
        manifest = dict(schema=1, library_sha256=digest(library), code_sha256=code,
                        spec_sha256=hashlib.sha256(json.dumps(self.spec, sort_keys=True).encode()).hexdigest(),
                        include_hashes=includes, platform=platform.platform(), python=platform.python_version(),
                        threads=1, solver=self.spec['solver'])
        write_json(self.directory/'manifest.json', manifest)
        (self.directory/'circuit.cir').write_text(self.spec['deck'])
        self.lib = C.CDLL(library)
        self.callbacks = [CHAR(self.message), CHAR(lambda *a:0), EXIT(self.exited),
                          DATA(self.data), INIT(self.init_data), BG(self.background)]
        self.sources = [SOURCE(self.source), SOURCE(self.source), SYNC(self.sync)]
        self.lib.ngSpice_Init.argtypes = [CHAR, CHAR, EXIT, DATA, INIT, BG, C.c_void_p]
        self.lib.ngSpice_Init_Sync.argtypes = [SOURCE, SOURCE, SYNC, C.POINTER(I), C.c_void_p]
        self.lib.ngSpice_Command.argtypes = [C.c_char_p]
        self.lib.ngSpice_Circ.argtypes = [C.POINTER(C.c_char_p)]
        self.lib.ngSpice_Init(*self.callbacks, None)
        self.ident = I(0)
        self.lib.ngSpice_Init_Sync(*self.sources, C.byref(self.ident), None)
        self.command('set num_threads=1')
        if self.spec['compatibility'] != 'native':
            self.command('set ngbehavior='+self.spec['compatibility'])
        lines = [line.encode() for line in self.spec['deck'].splitlines()]
        self.netlist_array = (C.c_char_p*(len(lines)+1))(*lines, None)
        if self.lib.ngSpice_Circ(self.netlist_array) != 0:
            raise RuntimeError('ngSpice_Circ failed; inspect ngspice.log')
        if self.spec['solver'] == 'klu':
            self.command('option klu')
        self.command('bg_run')
        self.wait()
        self.record(dict(kind='created', observation=self.observe()))

    def command(self, text):
        result = self.lib.ngSpice_Command(text.encode())
        if result:
            raise RuntimeError(f'ngspice command failed ({result}): {text}')

    def record(self, event):
        self.log.write(json.dumps(event, allow_nan=False)+'\n')
        self.log.flush()
        os.fsync(self.log.fileno())

    def message(self, text, *_):
        if not self.messages.closed:
            self.messages.write(text.decode(errors='replace')+'\n')
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

    def init_data(self, info, *_):
        try:
            self.signals = [info.contents.vectors[i].contents.name.decode().lower()
                            for i in range(info.contents.count)]
        except Exception as exc:
            self.failure = 'Vector metadata: '+str(exc)
        return 0

    def source(self, result, time_s, name, *_):
        try:
            result[0] = self.schedule.value(name.decode().lower(), time_s)
        except Exception as exc:
            result[0] = 0.0
            self.failure = 'External source: '+str(exc)
        return 0

    def data(self, values, *_):
        if self.closing or self.failure:
            return 0
        try:
            v = values.contents
            row = {v.values[k].contents.name.decode().lower():v.values[k].contents.real for k in range(v.count)}
            if 'time' in row:
                if len(self.rows) >= self.spec['max_samples']:
                    raise RuntimeError('Accepted sample budget exhausted')
                if not all(math.isfinite(value) for value in row.values()):
                    raise RuntimeError('Non-finite waveform value')
                self.rows.append(row)
                self.wave.write(json.dumps(row, allow_nan=False)+'\n')
        except Exception as exc:
            self.failure = str(exc)
        return 0

    def sync(self, time_s, delta, olddelta, redo, ident, loc, user):
        if loc == 0:
            with self.cv:
                self.now = time_s
                tolerance = time_tolerance(self.target)
                if not self.closing and (time_s >= self.target-tolerance or self.failure):
                    self.parked = True
                    self.wave.flush()
                    self.cv.notify_all()
                    while self.parked and not self.closing:
                        self.cv.wait()
        if not self.closing:
            delta[0] = self.schedule.limit_step(time_s, delta[0], self.target)
        return 0

    def wait(self):
        with self.cv:
            if not self.cv.wait_for(lambda:self.parked or self.done, timeout=60):
                self.failure = 'Wall-clock timeout waiting for ngspice barrier'
                raise TimeoutError(self.failure)
            if self.failure:
                raise RuntimeError(self.failure)
            if self.done and not self.parked:
                raise RuntimeError('ngspice ended before the requested barrier; inspect ngspice.log')

    def observe(self):
        last = self.rows[-1] if self.rows else {}
        return dict(epoch=self.epoch, time_s=self.now, time_hex=self.now.hex(),
                    state='failed' if self.failure else 'parked' if self.parked else 'finished' if self.done else 'running',
                    accepted_points=len(self.rows), last_sample=dict(last), stop_reason='failure' if self.failure else 'time',
                    horizon_s=self.spec['stop_time_s'], failure=self.failure)

    def metadata(self):
        return dict(signals=[dict(name=n,unit=unit(n)) for n in self.signals],
                    controls=[dict(name=n,unit='V' if c['kind']=='v' else 'A',**c) for n,c in self.spec['controls'].items()],
                    capabilities=dict(time_stepping=True, source_ramps=['linear','smoothstep'],
                                      event_stopping=False, live_topology_changes=False, analysis='transient'))

    def mutate(self, request):
        key = request.get('request_id')
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise ValueError('request_id must contain 1..128 characters')
        encoded = json.dumps(request, sort_keys=True, allow_nan=False)
        if key in self.cache:
            old, response = self.cache[key]
            if encoded != old:
                raise ValueError('request_id reused with different arguments')
            return response
        if self.failure or not self.parked:
            raise ValueError('Simulation is not parked and healthy')
        if type(request.get('expected_epoch')) is not int or request['expected_epoch'] != self.epoch:
            raise ValueError('Stale or invalid expected_epoch')
        explanation = request.get('explanation')
        if not isinstance(explanation, str) or not 1 <= len(explanation.strip()) <= 4000:
            raise ValueError('Provide a brief explanation (1..4000 characters)')
        method = request['method']
        ramps = None
        if method == 'schedule':
            ramps = self.schedule.prepare(request['updates'], self.now, self.spec['stop_time_s'])
        elif method == 'advance':
            target = finite(request['until_time_s'], 'until_time_s')
            if not self.now < target <= self.spec['stop_time_s']:
                raise ValueError('Advance time must be after current time and within the horizon')
            if target-self.now <= time_tolerance(target):
                raise ValueError('Advance interval is below the time synchronization tolerance')
        else:
            raise ValueError('Unsupported mutation')
        self.record(dict(kind='committed', request=request))
        try:
            with self.cv:
                self.epoch += 1
                if method == 'schedule':
                    self.schedule.commit(ramps)
                else:
                    self.target = target
                    self.parked = False
                    self.cv.notify_all()
            if method == 'advance':
                self.wait()
            result = self.observe()
            self.record(dict(kind='result', request_id=key, observation=result))
            self.cache[key] = (encoded, result)
            return result
        except Exception as exc:
            self.failure = str(exc)
            self.record(dict(kind='failed', request_id=key, error=str(exc)))
            raise

    def get_waveforms(self, request):
        if not self.parked or self.failure:
            raise ValueError('Waveforms require a healthy parked snapshot')
        expected = request.get('expected_epoch')
        if expected is not None and (type(expected) is not int or expected != self.epoch):
            raise ValueError('Stale waveform snapshot')
        names = request['signals']
        if not isinstance(names,list) or not 1 <= len(names) <= 64:
            raise ValueError('Select 1..64 saved signals')
        names = [signal_name(name) for name in names]
        if len(set(names)) != len(names) or 'time' in names or any(n not in self.signals for n in names):
            raise ValueError('Select unique saved signals; time is included automatically')
        end = finite(request['end_time_s'], 'end_time_s')
        if end > self.now + time_tolerance(self.now):
            raise ValueError('Waveform range extends beyond the current snapshot')
        result = waveform(self.rows, names, request['start_time_s'], end,
                          request.get('max_points',1000), request.get('reduction','minmax'), request.get('cursor',0))
        return dict(epoch=self.epoch, snapshot_time_s=self.now, **result)

    def close(self):
        final = self.observe()
        with self.cv:
            self.closing = True
            self.parked = False
            self.cv.notify_all()
        self.command('bg_halt')
        self.record(dict(kind='closed', observation=final))
        for stream in [self.wave,self.log,self.messages]:
            stream.close()
        return final


def main():
    engine = None
    try:
        engine = Engine(sys.argv[1], sys.argv[2])
        print(json.dumps(dict(ok=True, result=dict(observation=engine.observe(), **engine.metadata()))), flush=True)
        for line in sys.stdin:
            try:
                request = json.loads(line)
                method = request['method']
                if method == 'close':
                    result = engine.close()
                    engine = None
                elif method == 'observe':
                    result = engine.observe()
                elif method == 'metadata':
                    result = engine.metadata()
                elif method == 'waveforms':
                    result = engine.get_waveforms(request)
                else:
                    result = engine.mutate(request)
                print(json.dumps(dict(ok=True, result=result), allow_nan=False), flush=True)
                if engine is None:
                    break
            except Exception as exc:
                print(json.dumps(dict(ok=False, error=str(exc))), flush=True)
    finally:
        if engine:
            engine.close()

if __name__ == '__main__':
    main()
