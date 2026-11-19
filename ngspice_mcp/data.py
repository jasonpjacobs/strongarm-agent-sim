"""Pure validation, deterministic stimuli and waveform queries."""
import bisect
import hashlib
import json
import math
from pathlib import Path
import re
import shlex


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(value)


def time_tolerance(time_s):
    """Allow accumulated timestep roundoff without a circuit-specific time scale."""
    return max(64 * math.ulp(time_s), abs(time_s) * 1e-12)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def signal_name(name):
    if not isinstance(name, str):
        raise ValueError('Signal names must be strings')
    name = name.lower()
    if name.startswith('v(') and name.endswith(')'):
        return name[2:-1]
    if name.startswith('i(') and name.endswith(')'):
        return name[2:-1]+'#branch'
    return name


def unit(name):
    return 's' if name == 'time' else 'A' if name.endswith('#branch') else None if name.startswith('@') else 'V'


def include_files(text, directory, found=None):
    """Resolve and hash .include/.lib closure, including all corner sections."""
    found = {} if found is None else found
    for line in text.splitlines():
        if re.match(r'^\s*\.(?:include|inc|lib)\s', line, re.I):
            fields = shlex.split(line)
            if fields[0].lower() == '.lib' and len(fields) == 2:
                continue  # .lib tt starts a section inside a model file
            if len(fields) < 2:
                raise ValueError('Missing include filename')
            child = (Path(directory)/fields[1]).resolve()
            if str(child) not in found:
                found[str(child)] = digest(child)
                include_files(child.read_text(), child.parent, found)
    return found


def prepare_spec(netlist_path, stop_time_s, max_step_s, controls, solver='sparse', compatibility='native', max_samples=500000):
    path = Path(netlist_path).resolve()
    text = path.read_text()
    stop, step = finite(stop_time_s, 'stop_time_s'), finite(max_step_s, 'max_step_s')
    if not 0 < step <= stop:
        raise ValueError('Require 0 < max_step_s <= stop_time_s')
    if not math.isfinite(stop+2*step) or stop+2*step == stop:
        raise ValueError('Horizon and maximum step must permit a finite, representable analysis tail')
    if solver not in ('sparse', 'klu') or compatibility not in ('native', 'hsa'):
        raise ValueError('Unsupported solver or compatibility mode')
    if type(max_samples) is not int or not 10 <= max_samples <= 2000000:
        raise ValueError('max_samples must be an integer in [10,2000000]')
    # This is a trusted local circuit API, not an arbitrary ngspice command API.
    if re.search(r'^\s*\.(?:control|ac|dc|noise|op|pz|tf|sens|four)\b', text, re.I|re.M):
        raise ValueError('Supply a transient circuit without .control or other analysis directives')
    if not re.search(r'^\s*\.end\s*$', text, re.I|re.M):
        raise ValueError('Circuit requires a .end line')
    external = {}
    for line in text.splitlines()[1:]:  # SPICE's first line is always a title.
        fields = line.lower().split()
        if fields and fields[0][0] in 'vi' and 'external' in fields:
            if len(fields) != 6 or fields[3:] != ['dc', '0', 'external']:
                raise ValueError('External sources must use: NAME N+ N- dc 0 external')
            external[fields[0]] = fields[0][0]
    if not isinstance(controls, dict):
        raise ValueError('controls must map external source names to initial/min/max values')
    normalized = {}
    for name, cfg in controls.items():
        key = name.lower()
        if key in normalized or key not in external or set(cfg) != {'initial', 'min', 'max'}:
            raise ValueError('Each declared external source needs unique initial/min/max controls')
        initial, low, high = [finite(cfg[k], k) for k in ('initial', 'min', 'max')]
        if not low <= initial <= high or low == high:
            raise ValueError('Initial source value must be within ordered bounds')
        normalized[key] = dict(initial=initial, min=low, max=high, kind=external[key])
    if set(normalized) != set(external):
        raise ValueError('Declare controls for every top-level external voltage/current source')
    lines = []
    for line in text.splitlines():
        if re.match(r'^\s*\.tran\b', line, re.I):
            continue
        if re.match(r'^\s*\.end\s*$', line, re.I):
            # The extra tail keeps the horizon itself a resumable sync barrier.
            lines.append(f'.tran {step:.17g} {stop+2*step:.17g} 0 {step:.17g}')
        lines.append(line)
    return dict(schema=1, deck='\n'.join(lines)+'\n', circuit_directory=str(path.parent),
                stop_time_s=stop, max_step_s=step, controls=normalized, solver=solver,
                compatibility=compatibility, max_samples=max_samples)


class Schedule:
    def __init__(self, controls):
        self.controls = controls
        self.ramps = {name: [] for name in controls}

    def value(self, name, time_s):
        value = self.controls[name]['initial']
        for start, end, initial, final, shape in self.ramps[name]:
            if time_s < start:
                break
            if time_s < end:
                x = (time_s-start)/(end-start)
                return initial+(final-initial)*(x if shape == 'linear' else x*x*(3-2*x))
            value = final
        return value

    def prepare(self, updates, now, horizon):
        if not isinstance(updates, list) or not 1 <= len(updates) <= 64:
            raise ValueError('Provide 1..64 source updates')
        result = []
        ends = {n: r[-1][1] if r else now for n,r in self.ramps.items()}
        for u in updates:
            if set(u) != {'source', 'value', 'start_time_s', 'transition_s', 'shape'}:
                raise ValueError('Source update fields do not match schema')
            name = u['source'].lower()
            if name not in self.controls:
                raise ValueError('Unknown external source: '+name)
            start = finite(u['start_time_s'], 'start_time_s')
            duration = finite(u['transition_s'], 'transition_s')
            value = finite(u['value'], 'value')
            if start < now or start < ends[name] or duration <= 0 or start+duration > horizon or start+duration == start:
                raise ValueError('Ramps must be future, non-overlapping, nonzero duration and within the horizon')
            if u['shape'] not in ('linear', 'smoothstep'):
                raise ValueError('shape must be linear or smoothstep')
            if not self.controls[name]['min'] <= value <= self.controls[name]['max']:
                raise ValueError('Source value is outside configured bounds')
            previous = next((r[1][3] for r in reversed(result) if r[0] == name), self.value(name, start))
            result.append((name, [start, start+duration, previous, value, u['shape']]))
            ends[name] = start+duration
        return result

    def commit(self, ramps):
        for name, ramp in ramps:
            self.ramps[name].append(ramp)

    def limit_step(self, time_s, delta, target):
        # Repeatedly requesting a residual of a few ULPs can drive ngspice below
        # its minimum timestep. A boundary within roundoff is already reached.
        boundary = target if target-time_s > time_tolerance(target) else math.inf
        for ramps in self.ramps.values():
            for start, end, *_ in ramps:
                if start-time_s > time_tolerance(start):
                    boundary = min(boundary, start)
                if end-time_s > time_tolerance(end):
                    boundary = min(boundary, end)
                if start <= time_s < end:
                    delta = min(delta, (end-start)/20)
        return min(delta, boundary-time_s)


def waveform(rows, names, start_time_s, end_time_s, max_points=1000, reduction='minmax', cursor=0):
    start, end = finite(start_time_s, 'start_time_s'), finite(end_time_s, 'end_time_s')
    if start < 0 or end < start:
        raise ValueError('Require 0 <= start_time_s <= end_time_s')
    if type(max_points) is not int or not 2 <= max_points <= 10000:
        raise ValueError('max_points must be in [2,10000]')
    if type(cursor) is not int or cursor < 0 or (cursor and reduction != 'none'):
        raise ValueError('cursor is a nonnegative raw-sample offset; only valid with reduction=none')
    times = [r['time'] for r in rows]
    subset = rows[bisect.bisect_left(times, start):bisect.bisect_right(times, end)]
    if cursor > len(subset):
        raise ValueError('cursor exceeds query size')
    next_cursor = None
    if reduction == 'none':
        chosen = subset[cursor:cursor+max_points]
        if cursor+len(chosen) < len(subset):
            next_cursor = cursor+len(chosen)
    elif reduction == 'minmax':
        if max_points < 2*len(names)+4:
            raise ValueError('minmax budget must be at least 2 * signal_count + 4')
        if len(subset) <= max_points:
            chosen = subset
        else:
            buckets = (max_points-2)//(2*len(names)+2)
            indices = {0, len(subset)-1}
            for i in range(buckets):
                first, last = i*len(subset)//buckets, (i+1)*len(subset)//buckets
                indices.update([first, last-1])
                for name in names:
                    indices.add(min(range(first,last), key=lambda j:subset[j][name]))
                    indices.add(max(range(first,last), key=lambda j:subset[j][name]))
            chosen = [subset[i] for i in sorted(indices)]
    else:
        raise ValueError('reduction must be none or minmax')
    return dict(columns=['time']+names, units=['s']+[unit(n) for n in names],
                points=[[r['time']]+[r[n] for n in names] for r in chosen],
                available_points=len(subset), returned_points=len(chosen), next_cursor=next_cursor,
                reduction=reduction, interpolated=False)
