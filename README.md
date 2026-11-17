# QueuePact

**Queue coordination and decision testing for college admissions — Phase 4**

A focused scheduling evaluation adds explicit **QueuePact v1** and **QueuePact v2 (experimental)** choices. V2 did not establish an overall improvement; defaults and historical v1 behaviour are preserved. See [diagnosis, benchmark and adoption decision](docs/scheduling.md).

Phase 4 adds SQLite saved history and named scenario copies, immutable evidence snapshots, CSV ZIP and reproducibility JSON import/export, printable HTML impact reports, three honest demonstration presets, guided presentation mode and a reliable local launcher. [Phase 4 guide](docs/phase4.md) includes storage/backup details, architecture, presentation scripts and viva answers. The application remains a local educational prototype, not a production admissions system.

A Python-major educational simulation with a presentation-oriented NiceGUI browser interface and a headless SimPy engine. Phase 2 adds a persistent animated SVG hall, visit passports, desk closures, service slowdowns, deterministic arrival surges, a congestion spotlight and a filtered decision feed. It does not predict or guarantee improvements in real admissions halls.

Phase 3 adds **Comparison Lab** at `/lab`: synchronized Ordinary/QueuePact runs, four Plotly charts, fixed-horizon population-aware metrics, exhaustive extra-worker placement trials, deterministic reconstruction and additive branches, and explicit early-screening versus late-discovery operational scenarios. Live Operations remains at `/`.

Read [Phase 3 definitions, assumptions and demonstration](docs/phase3.md) and [verification evidence](verification/README.md). No scheduling policy or demo inputs were tuned. The baseline demo still averages **23.37 minutes Ordinary versus 27.55 minutes QueuePact**.

Read [Phase 2 behavior and two-minute demonstration](docs/phase2.md) for action semantics, animation, presenter architecture and limitations. [Verification notes](verification/README.md) preserve the Phase 1 evidence and record the new checks. The engine foundations and metric definitions below remain applicable; Phase 2 action/lifecycle details supersede the historical Phase 1 interface description.

## Windows PowerShell quick start

Tested on Windows with Python **3.14.3**, NiceGUI **3.16.0**, SimPy **4.1.2**, Plotly **6.9.0**, and pytest **9.1.1**. Plotly uses narwhals **2.25.0**. Python 3.11+ is declared compatible; only 3.14.3 was executed here. `requirements-tested.txt` records all installed dependency versions.

```powershell
Set-Location 'C:\Users\KIIT0001\OneDrive\Documents\ChatGPT\QueuePact'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-tested.txt
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe verification\verify_phase3.py
.\.venv\Scripts\python.exe -m queuepact headless --scenario examples/demo.json --policy both --output verification/demo
.\.venv\Scripts\python.exe -m queuepact ui
```

Open **http://127.0.0.1:8080**; `/lab` is Comparison Lab and `/history` is saved evidence. Stop with Ctrl+C. No virtual-environment activation or execution-policy changes are required. If the port is occupied, use `--port 8081`. The UI listens on loopback only. Installation initially needs package access; normal runs need no external services. Default storage is `%LOCALAPPDATA%\QueuePact\queuepact.sqlite3`; set `QUEUEPACT_DB` to an absolute path to override. Saved records are shared, but mutable runs remain isolated.

Run the small, hand-checkable fixture or a disruption experiment:

```powershell
.\.venv\Scripts\python.exe -m queuepact headless --scenario examples/small.json --policy ordinary
.\.venv\Scripts\python.exe -m queuepact headless --scenario examples/demo.json --policy both --actions examples/actions.json --output verification/disruption
```

`--policy both` generates **one immutable workload** and passes the same tuple to each engine. Output includes each policy's event JSON, a summary, the workload and action inputs. These are diagnostic simulation artifacts, not a Phase 2 report system.

## Project structure

```text
pyproject.toml                 package, entry point, pytest configuration
requirements-tested.txt       exact tested dependency environment
src/queuepact/
  __main__.py                 headless/UI commands
  models.py                   dataclasses, enums, validation, immutable snapshots
  scenarios.py                isolated seeded workload generation and scenario JSON
  engine.py                   SimPy calendar, state transitions, queues and actions
  events.py                   immutable structured event records and JSON
  metrics.py                  authoritative state-derived summaries
  actions.py                  deterministic complete surge payloads
  presenters.py               hall, passport, congestion and event view models
  policies/__init__.py        prerequisites, candidates and fair dispatch ordering
  experiments/spec.py        immutable specifications, fingerprints, JSON run records
  experiments/coordinator.py bounded synchronized runs and observation horizons
  experiments/staffing.py     qualified one-worker candidate trials and ranking
  experiments/replay.py      deterministic reconstruction and additive branches
  experiments/readiness.py   explicit screening / failed-check operational models
  experiments/results.py     comparative metrics, findings and Plotly figures
  archive.py, repository.py   immutable evidence, validation and SQLite saved history
  exports.py, reports.py      full-precision CSV/JSON and printable HTML/SVG
  presets.py                 three deterministic demonstration inputs
  ui/history.py              save/export/import, historical results and reconstruction verification
  ui/presentation.py         guided captions and real preset controls
  ui/app.py                   per-browser NiceGUI shell and playback timer
  ui/controller.py            headless session controls, debounce and reset
  ui/hall.py, ui/hall.js       persistent keyed SVG, selection and interpolation
  ui/style.css                local presentation styling, no remote font dependency
  ui/lab.py, lab_controller.py Comparison Lab and session-local job lifecycle
tests/test_engine.py           small behavioral and invariant tests
tests/test_phase2.py           live experience regressions
tests/test_phase3.py           experiment, reconstruction and readiness regressions
examples/                     small, demo and counter-action JSON fixtures
verification/                 executed verification evidence
```

No applicable AGENTS.md or existing application was found during initial inspection. No paid services, AI APIs, database, Node application or cloud infrastructure were introduced.

## Workflow and modeling assumptions

All times are simulated **minutes**. Every student needs exactly one verification, photo, payment and enrollment. Verification requires ready documents; payment requires verification; enrollment requires all three preceding services. Photo is independent and may occur before verification.

A missing-document student performs one pre-generated, positive-duration preparation activity. It represents simplified self-service preparation/help, **not a staffed help counter**. There is no resource contention for preparation. A preparing student cannot queue for or receive another service. Preparation ends with documents ready, so missing documents alone never strand a student.

Each counter has one dedicated staff ID qualified for its single declared service. Staff movement, breaks and multi-skilled desk switching are outside this phase. Each open counter serves at most one student; all compatible desks draw from one queue per service. There is no travel time, abandonment, priority category, rework or document rejection.

Configuration includes seed, count, batch/regular/Poisson arrival pattern, positive arrivals/minute, four counter counts, four positive uniform service-duration ranges, missing fraction, preparation-duration range, fair-wait threshold and simulation-time safety limit. Zero capacity is legal for blocked-state experiments. `examples/small.json` has three ready students arriving together, one desk per service, and unit durations; ordinary visits finish at 4, 5 and 6 minutes with waits 0, 1 and 2.

The first arrival is at zero. Later Poisson interarrivals are exponential; regular interarrivals are `1/rate`; batch arrivals are all zero. A private `random.Random(seed)` generates every arrival, all four durations, initial readiness and preparation duration **before any policy runs**. Required durations are known to the heuristic in this educational model. There are no policy-dependent random draws or global random mutations.

## Scheduling rules suitable for a viva

**Ordinary:** prepare first if needed, then verification → photo → payment → enrollment. Each service queue is FCFS by queue entry sequence, with stable student-ID ties. All open, idle compatible desks are used; there are no artificial delays.

**QueuePact:** after arrival, preparation or service completion, enumerate eligible unfinished activities. For a service, compute:

```text
estimate = own duration + (queued service work + open desks' remaining busy work) / open desk count
```

A service with no open compatible desk is unavailable (JSON `null` estimate). Preparation's estimate is its own duration. Pick the smallest finite estimate; ties use verification, photo, payment, enrollment, preparation order. If all candidates are unavailable, retain a deterministic candidate in its shared queue. The score estimates the **next activity**, not the entire visit or a globally optimal schedule. Busy work is a simple aggregate approximation, not an exact prediction of dispatch time.

For missing documents, photo competes directly with preparation using these estimates. A faster photo can run first; after it completes, preparation is the only remaining eligible activity until documents are ready. This prevents endless deferral.

Normally a routing choice stays fixed. Only loss of *all* open capacity for the chosen service triggers reconsideration. If another candidate is available, the student leaves the old queue once and is represented by the new queue/preparation state; otherwise the shared queue remains intact. A partial closure does not cause queue hopping. Restoring a desk triggers dispatch.

**Fair-wait protection:** within a QueuePact service queue, eligible students whose accrued current waiting age reaches the threshold take precedence over non-protected students. Protected students use oldest waiting age, then stable ID; others use queue entry sequence, then ID. With normal FCFS this often changes nothing. It matters after closure-driven reassignment, where an older waiter joins behind newer arrivals. Reassignment preserves waiting age; if reassigned through preparation, its elapsed duration does not inflate waiting age. Service start ends that waiting episode. Fairness never bypasses prerequisites, interrupts active service, or creates capacity. It cannot guarantee a maximum wait under insufficient capacity.

Every routing event stores candidate task, own duration, queue work, remaining busy work, desk count, estimate, selected task, rule and reconsideration reason. Its readable explanation is generated from those recorded values. Fairness events include age, threshold and queue ordering.

## Engine API and deterministic ordering

```python
from queuepact.engine import Engine
from queuepact.models import Scenario, Policy, Action
from queuepact.scenarios import generate_workload

config = Scenario()
workload = generate_workload(config)
run = Engine(config, workload, Policy.SMART,
             actions=(Action(5, 'PHOTO_CAPTURE-1', 'close'),
                      Action(15, 'PHOTO_CAPTURE-1', 'restore')))
run.advance(until=2.5)        # inclusive time boundary
run.advance(max_events=10)    # bounded SimPy calendar events, not log records
run.run()                    # completion, stall, or configured time limit
snapshot = run.snapshot()    # frozen dataclasses containing only immutable values
metrics = run.metrics()      # frozen summary
events = run.events          # tuple of immutable records; details returns a copy
fresh = run.reset()          # new state, same original workload/policy and action log
```

The engine imports no NiceGUI code. SimPy owns the event calendar. A small scheduling adapter sets up triggered SimPy events with explicit priorities: **0 external actions, 1 service/preparation completion, 2 arrivals, 3 dispatch**. At equal priority and time, insertion order wins. Initial students are inserted by stable ID, desks by service order then desk number, and supplied equal-time actions retain input order. Completion/arrival callbacks route in that deterministic order; dispatch is coalesced after these transitions. Durations are strictly positive, so no zero-time service cycles occur. The priority adapter uses SimPy Event's `_ok`/`_value` trigger fields; dependency and stepping tests cover this isolated integration point.

Time advancement never schedules UI refresh events into the model. The presentation clock can move between calendar events; service callbacks always use their scheduled time. Different event budgets and playback time increments produce byte-equivalent serialized events and identical final metrics for the same scheduled inputs and tested runtime. One bounded step may stop within a timestamp; continue advancing to finish its remaining transitions.

`apply_action(Action(...))` validates the desk, action kind and finite non-past time within the safety limit, appends the input to the immutable exposed action log, and schedules it. It is processed on advancement. Closing a busy desk lets its current service finish, but disallows new starts. Repeated close/restore commands are safe and logged with a `changed` flag. Completed/limit runs require reset before actions.

Scheduled action lists can be rerun deterministically. Interactive commands apply at the already-observed clock boundary; preloading the same timestamps can place an action before other events that the user already observed at that timestamp. Likewise, preloading a future restore avoids an interim `run_stalled` observation. Full reproduction of interactive insertion checkpoints/branching is deferred; Phase 1 preserves the timestamped action log and deterministic **scheduled-input** runs, not a complete interactive replay system.

When no future event can progress the run, it emits `run_stalled` once and returns; restoring capacity can resume it. Repeated refreshes of a stalled run do not spin or add events. A stalled clock remains at its last event. A scheduled future restoration keeps the run progressing toward that event. The configured simulation-time limit produces a distinct `run_limit_reached` state; reaching it never counts as successful completion. Successful runs stop at the last visit completion, even if later irrelevant actions exist. Zero students completes at time zero with undefined averages.

## Metrics

* Arrived includes all arrivals observed so far. Completed counts finished visits. Unfinished includes both not-yet-arrived and arrived-but-incomplete students, each displayed separately.
* Waiting, in service and preparing are disjoint current-state counts. Per-service queue lengths count waiting students only, shared across that service's desks.
* Queue waiting is actual time in service queues, including unfinished waits and closure waits; it excludes preparation and service. Total accumulated queue wait covers **all arrived students**. Student rows include finished queue intervals plus their current interval.
* Average and P90 total queue wait cover **completed visits only**, including zero-wait visits. P90 is nearest rank: sort `n` totals, choose one-based rank `ceil(0.9*n)` (no interpolation).
* Longest current wait is the maximum current waiting-episode age among currently queued students, including closure-carried age but excluding preparation. With no queued students it is undefined.
* Average completed visit time is final completion minus arrival, so it includes queue waiting, preparation and counter services.
* Counter busy time includes completed service intervals plus elapsed active service. Utilization is busy time divided by elapsed simulated time **from zero to the current clock**, including closed periods in the denominator. An active service finishing after closure remains busy. This measures calendar utilization, not open-hours efficiency. At time zero utilization is undefined.
* Undefined statistics serialize as `null` and display as **—**. Completed-only averages are always accompanied by prominent unfinished counts.

## Live Operations interface and lifecycle

The desktop-first NiceGUI page has configuration, status/clock/policy, start, pause/resume, speed, reset, metric cards, persistent counter cards with close/restore controls, a paginated student table and recorded recent events. Configuration locks after Start until Reset, including while paused or completed. The UI caps input at 1000 students for responsiveness; headless scenarios are not capped.

Each page owns its own engine and one client-bound timer. Reset constructs a fresh run without constructing another timer and clears interactive disruptions. It retains the last scenario/workload until Start applies the editable settings. A browser reload starts a new session. The timer is cancelled on client deletion; brief network disconnection follows NiceGUI's client lifecycle rather than a shared global simulation loop. Playback uses 0.25-second ticks; 1× advances 1 simulated minute per real second. It affects viewing pace only. The engine's `reset()` retains the action log for scheduled reruns; the UI Reset intentionally starts a clean experiment.

## Verification and manual checklist

See `verification/README.md` for executed results. The suite checks prerequisites, exact-once tasks, exclusive student occupancy, desk capacity, missing documents, both policies, deterministic outputs and batching, common workload requirements, hand metrics, fairness, closures/restorations, zero students, stalled/limited states, fresh resets, JSON, and incomplete statistics.

1. Launch the UI, choose a policy and student count, then Start. Confirm settings lock, the clock advances and students change state.
2. Pause and confirm the clock stays fixed; Resume and confirm it advances. Change playback speed.
3. Close a busy desk. It should display Closing with its active student until that service finishes, then Closed; Restore should allow later starts.
4. Reset during playback. Expect Ready, time zero, no events, all desks open, and editable settings. Start again and check for a single-speed clock.
5. Open a second browser page. It should have its own Ready state and controls.
6. Run both headless policies and inspect status, unfinished counts, events and summary. Do not assume the smart policy must win.

## Phase boundary

Phase 1 is complete at the simulation/UI foundation. There is no optimization guarantee or empirical validation against a real institution. Workload distributions, exact known duration estimates, unlimited preparation capacity and dedicated staff are modeling simplifications. Floating-point reproducibility is tested within the recorded Python/dependency environment, not promised across arbitrary future runtimes.

Phase 2 implements the live admission experience; Phase 3 implements experiments; Phase 4 implements local persistence, export, printable reports and presentation packaging. See `docs/phase4.md` for the completed scope and executed checks. Authentication, deployment and real-world validation are not implemented.

Framework references used: [NiceGUI timers](https://nicegui.io/documentation/timer), [NiceGUI lifecycle events](https://nicegui.io/documentation/section_action_events), [NiceGUI tables](https://nicegui.io/documentation/table), [SimPy core](https://simpy.readthedocs.io/en/latest/api_reference/simpy.core.html), [SimPy events](https://simpy.readthedocs.io/en/latest/api_reference/simpy.events.html).
