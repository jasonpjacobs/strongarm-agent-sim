# Planned voltage/current event stops

Status: **design only**. The current server has time-based `advance` and reports
`event_stopping: false`. No event condition is silently emulated by a sampling
loop in the agent.

## Proposed API

Extend `advance` with optional crossing conditions. `until_time_s` remains a
mandatory absolute deadline, so a condition that never occurs cannot run
indefinitely. Keep the same session, epoch, request ID and explanation contract.

```json
{
  "session_id": "...",
  "request_id": "wait-for-droop-1",
  "expected_epoch": 4,
  "until_time_s": 0.0001,
  "explanation": "Measure the first supply droop below 0.95 V after the load change.",
  "stop_on": [{
    "id": "droop",
    "signal": "v(out)",
    "threshold": 0.95,
    "direction": "falling",
    "hysteresis": 0.002,
    "after_time_s": 0.00001
  }],
  "event_max_step_s": 0.00000001
}
```

A current condition uses a saved branch current such as `i(VSENSE)` and amperes
for both threshold and hysteresis. Current direction follows the named source's
SPICE reference direction. Require finite thresholds, nonnegative hysteresis,
valid saved vectors, unique IDs, a direction of `rising`, `falling`, or `either`,
and an arming time within the requested interval. No clock is part of this API.

The first implementation should support **any-of** conditions only. A return
would contain the ordinary observation plus:

- `stop_reason`: `event` or `time` (or a simulation failure).
- `events`: all conditions that trigger at that accepted sample, in caller order.
- Each event's ID, units, direction, threshold and two bracketing accepted
  `(time, value)` samples.
- An explicitly labeled interpolated crossing estimate, when a finite linear
  estimate exists. This estimate is distinct from `time_s`, the actual parked
  solver time.

## Detection and synchronization

1. Validate and journal the conditions atomically while the solver is parked.
2. Evaluate conditions only on accepted `SendData` samples. Rejected timesteps
   and Newton iterations must not trigger or advance detector state.
3. Record a pending event at the first matching accepted sample.
4. Park at the following safe synchronization callback, before taking another
   integration step. Return the associated sample and actual barrier time;
   assert that their times agree within synchronization tolerance.

For rising crossings, arm after observing `value <= threshold - hysteresis`,
then fire when an accepted pair satisfies `previous < threshold <= current`.
For falling crossings, arm at `value >= threshold + hysteresis`, then fire on
`previous > threshold >= current`. `either` maintains the two directional
arming states. Arming starts at `after_time_s`; samples before it do not count.
Touching equality fires only on entry from the appropriate side, not on a
plateau. A condition already beyond the threshold when activated does not
count as a new crossing. A future level predicate, if added, should be separate.

Hysteresis controls rearming and helps reject chatter; it does not change the
reported threshold. The first version stops on the first eligible crossing
and discards these one-shot conditions after returning. A later advance must
explicitly register its own conditions. Debounce/dwell, occurrence counts,
Boolean expressions and persistent subscriptions are later extensions.

If an event and the time deadline occur at the same accepted sample, report
the event and include `deadline_reached: true`. If no event occurs, return
`stop_reason: time` with an empty event list. If several crossing estimates
fall between the same accepted samples, return all of them in caller order;
do not imply their interpolated ordering proves their physical ordering.

## Accuracy and missed events

Accepted-sample detection brackets a crossing; it does **not** put the solver
exactly at the mathematical root. The stopped simulation remains at the upper
bracket time. An `event_max_step_s` limit can narrow brackets, but several
crossings or a short pulse between two accepted samples can still go unseen.
Return the measured bracket width so the client can judge the result. Extrema
in reduced waveform responses must not be used as the event detector.

Precise root stopping is a separate capability. It would require a validated
ngspice rollback/retry mechanism or replay from the start using a tighter time
grid around the bracket. The present engine cannot rewind its analog state.
A replay/refinement approach must return a **new run ID**, record the new
timestep settings, and distinguish the refined trajectory from exact replay
of the original run. Never change only the displayed timestamp to imply an
exact solver stop.

## Replay and implementation sequence

Journal event definitions, arming rules, timestep limits, brackets and fired
IDs with the same action/result records used today. Include detector code and
settings in provenance. During exact replay, re-evaluate the conditions and
verify the firing sample and reason; do not replace an event condition with
its old timestamp. This catches regressions that a time-only replay would hide.

Implement in this order:

1. Pure accepted-sample detector and tests for equality, initial levels,
   direction, hysteresis, arming times, simultaneous events and deadlines.
2. A pending-event handoff between data and synchronization callbacks, with
   failure and lifecycle tests; no model calls inside callbacks.
3. MCP schema/capability changes and journaling/replay verification.
4. RC voltage/current threshold tests with analytic crossing-time checks and
   explicit finite bracket widths. Include a deliberately undersampled pulse
   test to demonstrate the detection limit.
5. StrongArm output-resolution events as a client-level experiment. Clock
   edges, if useful, are ordinary voltage crossings in that circuit.

The implementation should remain opt-in until accepted-sample/barrier ordering
is tested on supported ngspice builds. ngspice's shared API provides data and
time-synchronization hooks, but those alone are not a portable arbitrary-state
rollback API. See the [shared-library documentation](https://ngspice.sourceforge.io/shared.html).
