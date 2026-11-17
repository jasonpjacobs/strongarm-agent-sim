"""JSON-lines transport to one local simulator worker process."""
import json
from pathlib import Path
import select
import subprocess
import sys
from .config import ROOT

class Simulator:
    def __init__(self, folder, offset=.043, max_step=5e-12, reltol=1e-5):
        self.folder = Path(folder).resolve()
        self.folder.parent.mkdir(parents=True, exist_ok=True)
        if self.folder.exists():
            raise FileExistsError(f'Refusing to overwrite an existing run: {self.folder}')
        self.stderr = self.folder.with_name(self.folder.name+'-worker-stderr.log').open('w')
        self.p = subprocess.Popen([sys.executable, '-m', 'strongarm_sim.worker', str(self.folder),
                                   str(offset), str(max_step), str(reltol)], cwd=ROOT,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr, text=True)
        try:
            self.initial = self.read()
        except BaseException:
            self.close()
            raise

    def read(self):
        if not select.select([self.p.stdout], [], [], 75)[0]:
            raise TimeoutError('Simulator timed out; inspect the worker stderr and ngspice.log')
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError(f'Simulator exited; inspect {self.stderr.name}')
        obj = json.loads(line)
        if not obj['ok']:
            raise ValueError(obj['error'])
        return obj['result']

    def call(self, request):
        self.p.stdin.write(json.dumps(request, allow_nan=False)+'\n')
        self.p.stdin.flush()
        return self.read()

    def close(self):
        try:
            if self.p.poll() is None:
                self.p.stdin.write('{"method":"close"}\n')
                self.p.stdin.flush()
                self.p.stdin.close()
                self.p.wait(timeout=20)
        except (BrokenPipeError, subprocess.TimeoutExpired):
            self.p.terminate()
            try:
                self.p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait()
        finally:
            self.stderr.close()

    def excerpt(self, observation):
        if not observation['epoch']:
            return []
        start = (observation['epoch']-1)*20e-9
        rows = [r for line in (self.folder/'waveforms.jsonl').read_text().splitlines()
                if start <= (r := json.loads(line))['time'] <= observation['time_s']]
        if not rows:
            raise RuntimeError('No accepted waveform samples for the latest trial')
        indices = sorted({round(i*(len(rows)-1)/31) for i in range(32)})
        return [dict(time_ns=rows[i]['time']*1e9, clk_V=rows[i]['clk'],
                     external_diff_mV=(rows[i]['inp_ext']-rows[i]['inn'])*1e3,
                     outp_V=rows[i]['outp'], outn_V=rows[i]['outn']) for i in indices]
