# Phase 3 — Comparison and Experiment Lab

Open `/lab` from the navigation. Live Operations remains at `/`. Each page/client owns its mutable controller; opening a second tab starts an independent run. Keep Live Operations in its own tab when using the lab. No lab trial mutates a Live Operations engine.

## Run the project

```powershell
Set-Location 'C:\Users\KIIT0001\OneDrive\Documents\ChatGPT\QueuePact'
# First installation only; use the existing virtual environment when present:
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-tested.txt
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe verification\verify_phase3.py
.\.venv\Scripts\python.exe -m queuepact ui --port 8080
```

Visit `http://127.0.0.1:8080/lab`. Use another `--port` if occupied. The headless verification command writes raw acceptance evidence under `verification/`; it is not a final report feature. The original `python -m queuepact headless --policy both` command is unchanged.

## Definitions and fair inputs

`ExperimentSpec` is frozen and contains the scenario (including dedicated desk/worker resources), immutable generated workload, policies, ordered timestamped actions, modelling assumptions and schema version. Its stable fingerprint hashes canonical JSON. A `RunRecord` additionally records the selected policy and optional readiness configuration; its fingerprint includes those values. JSON round-trips validate schema and inputs. No live SimPy generator is serialized.

Both policy engines share exactly the same immutable workload and action payloads, but have separate students, counters, queues and event calendars. A surge is generated once and applied to both at the common simulated boundary. Shared actions are disabled after either side terminates or while a boundary is unfinished. Validation occurs before either run is mutated. Repeated identical UI action clicks within 0.8 seconds are rejected.

The regular playback timer requests a common time boundary every 250 ms. Each tick processes at most 200 calendar events per engine. A partial boundary is not rendered as a synchronized pair. Run to results requests ten-minute windows using the same event budget, yielding to the server between chunks; it never calls an unbounded run in a UI callback. Pause settles an already-requested boundary before freezing. Reset/cancel invalidates the generation token, so an older preparation callback cannot install a result. Reconstruction setup is bounded by input limits and runs in a worker thread; cancellation discards its result, while ongoing simulation chunks stop immediately. There is one timer per page, cancelled on client deletion.

Lab limits are 1000 base students, 100 recorded actions, 40 base desks and 10000 simulated minutes; each surge remains limited to 30 students over at most ten minutes. Candidate trials comprise at most a reference and four service placements. Session source history keeps at most 12 immutable records. These are local educational trials, not production performance guarantees.

## Completion, horizons and metrics

The engine processes all calendar events through an inclusive requested timestamp, subject to its event budget. A completed run freezes at its own finish time while the other continues. A pending future surge prevents premature completion. Known future surge students are included in lab unfinished/not-arrived counts before their action fires.

With an end time, completed visits and unfinished visits are both prominent. Accrued waiting includes all arrived students, including those still waiting or in service/preparation. A blocked queue continues accumulating waiting through a fixed observation horizon, even though no service can progress. Completion, blocked, safety-limit, horizon-reached and cancelled outcomes remain distinct. A run that finishes before the horizon keeps its completion measurement window.

Queue wait excludes counter service and document preparation; screening queue wait is included in readiness trials, but screening service is not waiting. Average, nearest-rank p90 and maximum wait cover **completed visits only**. Visit duration is finish minus arrival. Makespan is shown only for a fully completed run. Undefined values display an em dash. Differences are measured values; zero-reference percentages are unavailable rather than divided by zero. There is no winner badge.

Counter utilization is busy time divided by the calendar window **0 to that run's measured end**, including closure time. For an added counter, the denominator also includes the period before it was added; this is explicitly a calendar-window comparison, not utilization since assignment. Completed runs do not acquire idle tail time from the other panel. Screening worker busy minutes are disclosed separately from verification counter utilization.

The charts derive from timestamped events, never browser refreshes: completed visits and queue lengths use step lines after all events at each recorded timestamp; completed wait uses a box/point distribution; utilization uses each run's stated window. Charts refresh on pause/completion or explicitly with Refresh charts. Full events remain in the engine.

## Extra staff

Select a source record, assignment time, evaluation end time, worker qualifications, and services with spare compatible desks. Feasible services are the intersection of qualifications and spare desks in stable service order. Each independent candidate adds **one** worker at **one** service, with a unique deterministic desk ID. Existing multipliers apply to future starts at the added desk. Source inputs and recorded future disruptions remain unchanged. No training, movement or setup time is charged.

The reference adds no worker. Candidates rank by (1) most completed visits, (2) least total accrued waiting across all arrived students, (3) stable service order. Completed-only average wait is displayed as a trade-off, never the ranking objective. The chosen label means **best among tested placements for this scenario and objective**; the reference can still be better. An empty feasible set produces reference-only results with a clear explanation. Open selected candidate starts isolated reconstructions using that candidate's action record, without changing the source. The main two panels during a multi-candidate trial show the reference and first feasible candidate; the full placement table shows every candidate and the selected placement.

## Reconstruction and turning-point ordering

Capture/select a source, choose time T and an intervention. Rebuild from original inputs and the full action history, including future actions. Two independent engines process through T. The unchanged branch adds nothing; the intervention branch appends an action at T after the original boundary.

Calendar ordering is ordinary scheduled actions (priority 0), completions (1), arrivals (2), dispatch (3), then observed-boundary actions (4). Insertion order breaks equal-priority ties. A dispatch caused by a boundary action occurs before the next boundary action. Reconstruction processes **all original actions/events at T, including their resulting dispatches**, before the new action. The new action is appended, never substituted for an existing one. Future original actions remain and can later reverse a new closure or multiplier; the timeline shows both branches' ordered action markers and their payloads on hover.

Supported additive actions: close, restore, multiplier, one qualified worker/spare desk, deterministic surge. An intervention at/after terminal completion is rejected; choose an earlier time. The unchanged continuation reproduces original events and metrics. `normalized_events` removes only `run_stalled` diagnostic records (which depend on whether the caller observed an intermediate stall) and renumbers the remaining events. Raw ordinary uninterrupted runs also reproduce exactly. No arbitrary historical generator snapshot is claimed to be loaded.

## Readiness alternatives

These are explicit new operational models and do not alter the default engine or demo. One policy is held fixed across both. Arrivals, initial readiness flags, base service durations, preparation durations and any supplied actions are identical.

**Early screening:** all students first queue FCFS for a configured number of additional screening workers. Every student consumes a positive screening duration. Missing students then prepare immediately; ready students proceed under the selected policy. No admission service occurs while screening/preparing. Screening is a distinct prerequisite activity in this experiment, not completed document verification.

**Late discovery:** missing students first queue at verification. Their failed check occupies a normal verification desk for the configured positive discovery duration, adjusted by the active multiplier when it starts. It records `verification_check_started` and `verification_check_failed`, does not mark verification complete, and does not unlock payment. The student prepares immediately and rejoins for full verification. Ready students receive normal verification only; its base duration includes their check, so they are not charged an extra discovery visit. This compact model assumes initial flags determine who needs a failed attempt; it does not simulate probabilistic detection errors.

Preparation is the same explicit unstaffed timed activity as before, with all time retained separately. Early screening adds workers; this is **not a resource-equal policy comparison**. Results disclose screening staff and busy time, failed-check desk time, preparation time, completed/unfinished populations and wait/visit metrics. Readiness run records preserve the operational configuration for reconstruction. The compact readiness results use metric panels rather than pretending the four-zone hall contains a screening desk.

## Observed demo and interpretation

Seed 42, 40 students, unchanged base scenario:

| Measured outcome | Ordinary | QueuePact |
|---|---:|---:|
| Completed visits | 40 | 40 |
| Average queue wait | 23.368975 | 27.550248 |
| P90 queue wait | 35.880785 | 39.614489 |
| Maximum completed wait | 38.506961 | 40.918391 |
| Average visit duration | 34.539737 | 38.721010 |
| Makespan | 86.474101 | 87.223683 |
| Photo completed before verification | 0 | 22 |

Observed QueuePact average wait is **4.18 minutes higher**, with the same total completions and 167.25 more accumulated waiting minutes. Its routing score still chooses the eligible next activity with the smallest estimated completion: effective own duration plus queued work and open-desk remaining work divided by open desk count. It does not estimate downstream visit completion. The observed different task order and queue series are consistent with demand moving between stages. That is a possible explanation, not a demonstrated causal decomposition; no policy optimization or input tuning was done.

The default readiness trial is deliberately not curated to make early screening win: early average wait is 23.31 minutes, late 22.81. Screening costs 20.00 worker-minutes; late failed checks cost 7.50 verification desk-minutes; both retain 51.88 preparation minutes. See raw evidence in `verification/phase3-results.json`.

## Short demonstration

1. Start comparison; pause and inspect the two halls and unfinished counts. Use Run to results. Read the 4.18-minute higher QueuePact wait and both policies' 40 completions.
2. In Extra staff, use the captured Ordinary source, all qualifications/spare desks and a 60-minute horizon. Test placements. Compare the reference, selected placement and completed-only averages; open the selected candidate branch.
3. In Turning point, select the original Ordinary source, minute 10, and a 1.5× verification multiplier. Reconstruct & branch, then Run to results. The unchanged side keeps the original result; the timeline identifies the additive intervention.
4. In Document readiness, keep Ordinary, one screening worker, 0.5-minute screening and 0.75-minute failed checks. Compare readiness approaches and inspect the overhead alongside waiting.

## Limits and Phase 4

These deterministic trials assess one scenario, horizon and objective; they do not establish universal benefits or causal explanations. Real staffing qualifications, help-counter capacity, setup/travel time and detection uncertainty are not modelled. Background setup cancellation invalidates results rather than forcibly killing a Python worker thread. Page history is in memory and resets with the page. Lab records are JSON-capable in Python; import/export/history-management interfaces and final reports are deferred. Phase 4 remains presentation packaging, export and final polish; no authentication, deployment or cloud services were added.
