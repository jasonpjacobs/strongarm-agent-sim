# General-purpose ngspice MCP prototype

This is a local **transient simulation** server. An MCP host can inspect saved
waveforms, decide what to try, schedule voltage/current changes, and advance the
same simulation. The simulator stays parked while the agent thinks. There is no
clock, cycle, reset, common-mode voltage, threshold search, or latch classifier
in `ngspice_mcp/`.

The server is implemented in Python using the official MCP SDK and ngspice's
shared-library callbacks. MCP supplies the agent-facing interface; it does not
replace the simulator worker. Each session has its own worker process, since
independent libngspice instances must not share process-global simulator state.

## Setup

Use Python 3.11+ and a shared ngspice build on Linux or macOS. Windows users
should use Linux/WSL. A CLI-only ngspice installation is insufficient. Full
simulation testing currently uses Linux ARM64, ngspice 47 and Python 3.12.3.

```sh
./setup-mcp.sh --ngspice-library /path/to/libngspice.so
# macOS: pass libngspice.dylib instead.
```

Setup checks the shared-library entry points, installs `requirements-mcp.txt`
into the separate `.venv-mcp/` environment, and writes `.local/mcp-config.json`.
Use `PYTHON_BIN=/path/to/python3 ./setup-mcp.sh ...` to select Python.
`NGSPICE_LIBRARY` is also accepted as a discovery hint. Setup does not download
ngspice or a PDK, change shell startup files, or install/call a model client.
SKY130, the ngspice CLI, plotting packages and credentials are unnecessary for
the RC example. The original `setup.sh`/`run.sh` workflow remains separate.

Configure an MCP host with a local stdio server. For hosts using `mcpServers`
configuration, substitute the absolute checkout path:

```json
{
  "mcpServers": {
    "ngspice": {
      "command": "/absolute/path/strongarm-agent-sim/mcp.sh",
      "args": []
    }
  }
}
```

The launcher also accepts `--library`, `--workspace`, `--output`, `--config`,
and `--max-sessions`. Defaults are this checkout as workspace, `runs/mcp/` for
evidence, and four active sessions. A supplied library path takes precedence
over `NGSPICE_LIBRARY`, then local configuration. `MCP_PYTHON` can select an
existing environment with the pinned SDK installed. Run `./mcp.sh --help` for
options. The server uses stdin/stdout for MCP; it has no HTTP endpoint.

The host supplies the AI model and controls model-service access. The server
does no inference and contains no model-specific adapter. All mutating tools
require a brief `explanation`, which is stored with the exact action. Full
model responses and conversation history belong in the MCP host's own log;
the server cannot record text it never receives.

## Tools and units

All times are absolute seconds, source values are volts or amperes, and signal
names are case-insensitive. Creation returns `session_id`, `observation`,
signal/control metadata and capabilities. Subsequent observations include
`epoch`, actual solver `time_s`, exact `time_hex`, state, last accepted sample,
accepted point count, horizon and failure information.

| Tool | Purpose |
| --- | --- |
| `create_simulation` | Load a trusted circuit and park at time zero; set horizon, maximum timestep and control bounds |
| `list_signals_and_controls` | Discover saved vectors, units, controllable sources and capabilities |
| `observe` | Read current time, epoch and last accepted sample without advancing |
| `schedule_stimulus` | Atomically append one or more future voltage/current ramps; return the next epoch |
| `advance` | Continue to an absolute time, then park and return the next epoch |
| `get_waveforms` | Read a time window using raw pagination or extrema-preserving reduction |
| `close_simulation` | Finalize the run and release its worker; repeated closes are safe |
| `replay_experiment` | Re-execute a closed run's actions in another worker and verify exact replay |

Create a clock-free RC session with these `create_simulation` arguments:

```json
{
  "request_id": "rc-create-1",
  "circuit_path": "examples/mcp/rc.cir",
  "stop_time_s": 0.000006,
  "max_step_s": 0.00000001,
  "controls": {
    "vin": {"initial": 0, "min": -2, "max": 2},
    "iload": {"initial": 0, "min": 0, "max": 0.001}
  }
}
```

The circuit declares controls as `VIN in 0 dc 0 external` and
`ILOAD out 0 dc 0 external`. Every top-level external source must have a control
declaration. Other sources, including ordinary PULSE/PWL sources, can remain
in the netlist. Circuits without external controls use an empty controls map.
Existing `.tran` is replaced by the supplied settings; other analysis commands
and top-level `.control` blocks are rejected. Choose saved quantities using
`.save`, for example `.save v(in) v(out) i(VIN)`. This first version does not
expose transient `uic` or change the DC initialization procedure.

With the returned session ID and epoch 0, call `schedule_stimulus`:

```json
{
  "session_id": "RETURNED_SESSION_ID",
  "request_id": "charge-1",
  "expected_epoch": 0,
  "updates": [{
    "source": "vin",
    "value": 1,
    "start_time_s": 0.000001,
    "transition_s": 0.00000001,
    "shape": "linear"
  }],
  "explanation": "Apply a 1 V ramp to measure the RC charging response."
}
```

This returns epoch 1 at time zero. Then call `advance` with that epoch:

```json
{
  "session_id": "RETURNED_SESSION_ID",
  "request_id": "measure-1",
  "expected_epoch": 1,
  "until_time_s": 0.000002345,
  "explanation": "Inspect the partial settling response before choosing the next load."
}
```

Retrieve the history with `get_waveforms`:

```json
{
  "session_id": "RETURNED_SESSION_ID",
  "signals": ["v(out)", "i(VIN)"],
  "start_time_s": 0,
  "end_time_s": 0.000002345,
  "expected_epoch": 2,
  "max_points": 200,
  "reduction": "minmax"
}
```

The response has `columns`, `units`, row-oriented `points`, available/returned
point counts, snapshot time and epoch. `time` is always the first column.
`v(out)` aliases `out`; `i(VIN)` aliases `vin#branch`. Current follows ngspice's
reference direction. Device-property vectors beginning with `@` have unknown
units (`null`) in this prototype; ordinary node voltages and branch currents
are labeled V and A.

`minmax` retains first/last samples plus each selected signal's extrema within
sample-index buckets. It preserves narrow sampled spikes rather than uniformly
skipping points, but does not claim to reconstruct unsampled peaks. Its budget
must be at least `2 * signal_count + 4`. For exact history, use `reduction: "none"`
and pass each `next_cursor` back as `cursor`, keeping the same query and
`expected_epoch`. A null cursor means completion. Up to 64 signals and 10,000
rows per response are supported. No returned sample is interpolated.

An agent can now choose a new load, a new observation time, or stop based on
these results. A suitable host prompt is:

> Use the ngspice MCP tools to investigate the RC circuit. Create the session
> above, apply an initial input, and inspect its waveform. Then choose each
> subsequent current load and observation time from the measurements. Explain
> each experiment briefly in the tool's explanation field. Use at most six
> advances within 6 microseconds, close the session, and replay it. Report
> what you learned and the replay result.

## Synchronization and stimulus semantics

The shared-library synchronization callback parks at an accepted-time barrier.
It releases the Python condition lock while waiting. The worker command thread
can inspect history and append stimuli, then release the solver for `advance`.
The callback clamps proposed timesteps at upcoming source boundaries and the
requested stop time. During a transition it additionally limits the step to
one twentieth of its duration. Source callbacks are pure functions of time,
so Newton retries or rejected steps do not consume or alter the stimulus.

Boundary comparisons allow `max(64 * ulp(t), abs(t) * 1e-12)` seconds for
accumulated floating-point roundoff. The response reports the actual solver
time; it never substitutes the requested time. An advance smaller than this
tolerance is rejected. This numerical tolerance has no clock assumption.

Ramps use `linear` or `smoothstep` interpolation followed by a hold. Duration
must be positive; instantaneous discontinuities are not supported. Source
schedules are append-only and cannot overlap or rewrite history. Start time
must be at or after the current barrier and the previous ramp's endpoint;
the whole ramp must fit inside the horizon. A batch of 1–64 changes is validated
in full before any change commits. Different sources can change simultaneously.

Each successful schedule or advance increments a session-wide `epoch`. Supply
the latest epoch on every mutation. Per-session transport locking serializes
concurrent calls; only one of two mutations using the same epoch can commit.
An observation may be superseded immediately after it returns, so mutations
must still use the epoch check. Different sessions retain independent states.

`request_id` makes creation and mutation retries idempotent **during this server
lifetime**. An identical retry returns its original response, even if the
session has since advanced. Observe again if you need current state. Reusing
an ID with different arguments is an error. A client timeout is not evidence
that a mutation failed: reconnect to the still-running host transport and
retry the same request if possible. Restarting the server does not restore
live session IDs or idempotency caches; use a finalized run's replay instead.

## Logs and replay

Every run lives in `runs/mcp/<run_id>/` by default:

| File | Evidence |
| --- | --- |
| `spec.json`, `circuit.cir` | Frozen effective circuit, analysis and control configuration |
| `manifest.json`, `model-hashes.json` | Shared-library, backend code, recursively included model hashes, platform/Python and solver settings |
| `events.jsonl` | Initial observation, committed actions and explanations, result/failure records, final observation |
| `waveforms.jsonl` | Every saved vector at every accepted sample, regardless of query reduction |
| `closed.json` | Final observation of a finalized session |
| `ngspice.log`, `worker-stderr.log` | Simulator diagnostics |
| `replay-verification.json` | Successful replay's action/sample counts and equality results |

The worker flushes and fsyncs a commitment before changing a schedule or
releasing the solver. Waveform output is flushed at each barrier. These files
are diagnostic/replay evidence, not a transactionally recoverable checkpoint
or a tamper-proof audit service. A crash with a commitment but no result is
rejected by exact replay. A forced kill may leave an incomplete run.

Close the session, then call `replay_experiment` with the returned `run_id`.
Replay starts a new worker with the frozen circuit and recorded actions. It
compares provenance, the initial observation, every intermediate observation,
the final observation and all accepted samples. It makes zero model calls.
Only healthy finalized runs are accepted. Provenance mismatches or numerical
differences fail verification; there is no silent tolerance-based fallback.

Model files are hashed, not bundled: the recorded include paths must still
exist with identical contents. The platform, Python, library and backend code
must also match. This is local exact replay, not a cross-machine numerical
equivalence claim. Restarted servers can replay existing finalized run IDs
when configured with the same output directory. The original `run.sh` logs
use a different format and are not accepted by this new replay endpoint.

## StrongArm regression fixture

Clock timing and output classification live in the **test client and circuit**,
not the server. Generate the fixture using an installed open_pdks SKY130A tree:

```sh
python3 scripts/mcp_strongarm_fixture.py \
  --sky130-lib /path/to/sky130A/libs.tech/ngspice/sky130.lib.spice \
  --output runs/mcp-strongarm.cir

.venv-mcp/bin/python tests/integration/mcp_smoke.py \
  --library /path/to/libngspice.so \
  --sky130-lib /path/to/sky130A/libs.tech/ngspice/sky130.lib.spice \
  --output runs/mcp-smoke
```

Use a new output directory each time. Add `--solver klu` only when the shared
library supports KLU. The integration test starts the actual MCP stdio server,
runs the RC test, sends all 12 historical StrongArm stimuli, checks measured
polarities, and verifies exact local replay for both circuits. It also checks
idempotency, stale requests, concurrent mutations, invalid atomic batches,
raw waveform paging, altered replay provenance and orderly disconnect cleanup.
Additional checks cover independent sessions, sample-budget failure and replay
after restarting the server. Add `--launcher` after running setup to test
`mcp.sh` and its configuration instead of passing the library to the module.
This is a scripted regression client using recorded AI choices, **not a fresh
AI run**. New agent choices must come from an MCP host with a connected model.

The fixture exposes internal nodes for regression checks. The general server
does not enforce the original experiment's hidden-offset policy. For a blind
agent study, create a separate fixture saving only public signals and configure
the host's file/tool access accordingly. Do not claim the public fixture hides
the injected offset.

## Current limits and planned events

The server accepts trusted local circuits inside the configured workspace;
include files can be elsewhere, for example an installed PDK. It is **not a
netlist sandbox** and must not be exposed to untrusted remote clients. It does
not offer arbitrary ngspice commands or shell execution as MCP tools.

This version supports transient analysis, predeclared top-level external
sources, fixed saved signals, and in-memory waveform retention. There is no
live topology/model editing, DC/AC/noise analysis, arbitrary solver checkpoint,
or rewind. The default accepted-sample cap is 500,000 (configurable from 10 to
2,000,000); exceeding it fails the session. Many saved vectors can still consume
substantial memory. A worker has a 60-second wall-time budget for each advance
or initialization, with a 75-second transport timeout. A running call cannot
currently be canceled while preserving a usable session. Configure the host's
tool timeout to exceed this budget; a replay containing many advances can take
longer in total. Orderly disconnect closes workers.

**Event stopping is planned, not implemented.** Capabilities explicitly report
`event_stopping: false`. See [the voltage/current crossing design](event-stopping.md)
for the proposed API, hysteresis, event ordering, deadline behavior and the
difference between detecting a crossing and locating it precisely.

References: [ngspice shared-library interface](https://ngspice.sourceforge.io/shared.html),
[official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk),
and [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
