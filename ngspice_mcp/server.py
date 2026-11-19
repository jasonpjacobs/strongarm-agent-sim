"""Local MCP facade. Each simulation has its own worker and serialized transport."""
from contextlib import asynccontextmanager
from functools import wraps
import json
from pathlib import Path
import re
import threading
import uuid
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict

from .data import prepare_spec
from .session import Session, replay


def client_errors(function):
    """Expose actionable validation/backend failures through MCP tool results."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, OSError, RuntimeError, AssertionError) as exc:
            raise ToolError(str(exc)) from exc
    return wrapped


class Control(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    initial: float
    min: float
    max: float


class Stimulus(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source: str
    value: float
    start_time_s: float
    transition_s: float
    shape: str = 'linear'


class Manager:
    def __init__(self, library, workspace, output, max_sessions=4):
        self.library = str(Path(library).resolve())
        self.workspace = Path(workspace).resolve()
        self.output = Path(output).resolve()
        self.max_sessions = max_sessions
        self.sessions, self.creations = {}, {}
        self.lock = threading.RLock()

    def create(self, request_id, circuit_path, stop_time_s, max_step_s, controls,
               solver='sparse', compatibility='native', max_samples=500000):
        path = (self.workspace/circuit_path).resolve()
        if not path.is_relative_to(self.workspace):
            raise ValueError('Circuit must be inside the configured workspace')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError('Provide a creation request_id (1..128 characters)')
        args = dict(circuit_path=str(path), stop_time_s=stop_time_s, max_step_s=max_step_s,
                    controls=controls, solver=solver, compatibility=compatibility, max_samples=max_samples)
        encoded = json.dumps(args, sort_keys=True, allow_nan=False)
        with self.lock:
            if request_id in self.creations:
                previous, result = self.creations[request_id]
                if previous != encoded:
                    raise ValueError('Creation request_id reused with different arguments')
                return result
            if sum(not s.closed for s in self.sessions.values()) >= self.max_sessions:
                raise ValueError('Active simulation limit reached; close a session first')
            spec = prepare_spec(path, stop_time_s, max_step_s, controls, solver, compatibility, max_samples)
            session_id = uuid.uuid4().hex
            session = Session(self.output/session_id, self.library, spec)
            self.sessions[session_id] = session
            result = dict(session_id=session_id, **session.initial)
            self.creations[request_id] = encoded, result
            return result

    def get(self, session_id):
        with self.lock:
            if session_id not in self.sessions:
                raise ValueError('Unknown active session; server restart requires replay, not resume')
            return self.sessions[session_id]

    def replay(self, run_id):
        if not re.fullmatch('[0-9a-f]{32}', run_id):
            raise ValueError('Use a run ID returned by this server')
        with self.lock:
            if run_id in self.sessions and not self.sessions[run_id].closed:
                raise ValueError('Close the source simulation before replay')
            if sum(not s.closed for s in self.sessions.values()) >= self.max_sessions:
                raise ValueError('Active simulation limit reached; close a session first')
            replay_id = uuid.uuid4().hex
            result = replay(self.output/run_id, self.output/replay_id, self.library)
            return dict(run_id=replay_id, source_run_id=run_id, **result)

    def close(self):
        for session in list(self.sessions.values()):
            try:
                session.close()
            except Exception:
                session._terminate()


def make_server(manager):
    @asynccontextmanager
    async def lifespan(server):
        try:
            yield {}
        finally:
            manager.close()

    server = MCPServer('ngspice', version='0.1.0', lifespan=lifespan,
        instructions='Control general transient simulations. All times are absolute seconds. '
        'Simulation time is frozen between advance calls. Read metadata to discover saved signals and '
        'controllable sources. Carry the latest epoch into each mutation and use a stable request_id '
        'for retries. Supply a brief experimental explanation, not private reasoning. '
        'No clock, reset, input common mode or classification is imposed. Event stopping is planned, '
        'not currently supported. Close sessions before exact replay. This server performs no model inference.')

    @server.tool(structured_output=True)
    @client_errors
    def create_simulation(request_id: str, circuit_path: str, stop_time_s: float, max_step_s: float,
                          controls: dict[str, Control], solver: str='sparse', compatibility: str='native',
                          max_samples: int=500000) -> dict[str, Any]:
        """Load a trusted local SPICE circuit; return a persistent session parked at time zero.

        circuit_path is relative to the server workspace. Every controllable top-level V/I
        source must be declared as NAME N+ N- dc 0 external. Supply initial/min/max values
        in volts or amps. Existing .tran is replaced by these settings. Saved vectors come
        from the circuit's .save directives. Use hsa compatibility for supported SKY130 decks.
        Creation retries with the same request_id/arguments return the original response.
        """
        return manager.create(request_id, circuit_path, stop_time_s, max_step_s,
                              {k:v.model_dump() for k,v in controls.items()}, solver, compatibility, max_samples)

    @server.tool(structured_output=True)
    @client_errors
    def observe(session_id: str) -> dict[str, Any]:
        """Read the current epoch, simulation time and last accepted sample; never advance time."""
        return manager.get(session_id).call({'method':'observe'})

    @server.tool(structured_output=True)
    @client_errors
    def list_signals_and_controls(session_id: str) -> dict[str, Any]:
        """Discover exact saved-vector names, units, source bounds and backend capabilities."""
        return manager.get(session_id).call({'method':'metadata'})

    @server.tool(structured_output=True)
    @client_errors
    def schedule_stimulus(session_id: str, request_id: str, expected_epoch: int,
                          updates: list[Stimulus], explanation: str) -> dict[str, Any]:
        """Atomically append voltage/current ramps while parked; return the new epoch.

        Each ramp starts at an absolute future time, transitions over a positive duration
        using linear or smoothstep interpolation, then holds its final value. Ramps on a
        source cannot overlap or rewrite its existing schedule. Multiple sources may change
        together. This call does not advance simulation time. Retry with identical arguments.
        """
        return manager.get(session_id).call(dict(method='schedule', request_id=request_id,
            expected_epoch=expected_epoch, updates=[u.model_dump() for u in updates], explanation=explanation))

    @server.tool(structured_output=True)
    @client_errors
    def advance(session_id: str, request_id: str, expected_epoch: int,
                until_time_s: float, explanation: str) -> dict[str, Any]:
        """Advance the same transient to an absolute time, then park and return its new epoch.

        The target must be later than the current time and no later than stop_time_s.
        No implicit reset or clock-cycle rounding occurs. reported time_s is the actual
        solver barrier (tolerance max(64 ULPs, abs(target)*1e-12)).
        """
        return manager.get(session_id).call(dict(method='advance', request_id=request_id,
            expected_epoch=expected_epoch, until_time_s=until_time_s, explanation=explanation))

    @server.tool(structured_output=True)
    @client_errors
    def get_waveforms(session_id: str, signals: list[str], start_time_s: float, end_time_s: float,
                      max_points: int=1000, reduction: str='minmax', cursor: int=0,
                      expected_epoch: int|None=None) -> dict[str, Any]:
        """Read saved history up to the current pause; no advance and no interpolation.

        Native vector names and v(node)/i(voltage_source) aliases are accepted. Time is
        included automatically. minmax retains first/last and extrema in each index bucket;
        its budget must be >= 2*signal_count+4. none pages exact raw samples with next_cursor.
        Use the returned epoch as expected_epoch on subsequent pages to prevent stale reads.
        All accepted samples are retained in the run's waveform log regardless of reduction.
        """
        return manager.get(session_id).call(dict(method='waveforms', signals=signals,
            start_time_s=start_time_s, end_time_s=end_time_s, max_points=max_points,
            reduction=reduction, cursor=cursor, expected_epoch=expected_epoch))

    @server.tool(structured_output=True)
    @client_errors
    def close_simulation(session_id: str) -> dict[str, Any]:
        """Release the worker and finalize replay evidence. Repeated closes are safe."""
        session = manager.get(session_id)
        result = session.close()
        return dict(run_id=session_id, final_observation=result, state='closed')

    @server.tool(structured_output=True)
    @client_errors
    def replay_experiment(run_id: str) -> dict[str, Any]:
        """Replay a closed run in a new worker, verifying provenance, observations and samples.

        Uses committed actions without model calls. Each invocation creates a separate replay
        run. Incomplete/failed sessions are rejected. The same numerical environment is required.
        """
        return manager.replay(run_id)

    return server
