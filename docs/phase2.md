# Phase 2 — the live admission experience

QueuePact now has a custom SVG admission hall, shared student visit passports, a disruption panel, observable congestion insights and filtered recorded decisions. Its copy says **“Explore queue coordination and its effects.”** No policy optimization was performed.

## Launch on Windows PowerShell

```powershell
Set-Location 'C:\Users\KIIT0001\OneDrive\Documents\ChatGPT\QueuePact'
.\.venv\Scripts\python.exe -m queuepact ui
```

Open http://127.0.0.1:8080. Use `--port 8084` if another server occupies the default port. Installation commands remain in the main README. No dependencies were added; `requirements-tested.txt` still records Python 3.14.3's tested NiceGUI 3.16.0 / SimPy 4.1.2 / pytest 9.1.1 environment. SVG, CSS, system fonts and bundled NiceGUI assets are local.

## Layout and interaction

The navy header keeps policy, status and simulated clock visible. A sticky toolbar provides Start, Pause/Resume, Reset, playback, Disruptions and Configure. Navigation links lead to the live hall, student directory and decision feed. Configuration lives in a compact dialog and is locked after Start until Reset. The directory is collapsible and paginated.

The hall shows entrance, document preparation, verification, photo, payment, enrollment and exit. Desks use short stable IDs V1/V2, P1, F1/F2 and E1, mapped to full engine IDs by their service zones. Desks show Available, Serving, Closing or Closed; active student markers and progress come from scheduled start/finish times. Queue counts are shared service counts, not individual desk queues.

Seven waiting markers per service and four preparation markers are rendered, with `+N` overflow counts. The selected student is included in the bounded set even if outside its initial displayed slice. Every active desk has its student marker. Completed students become an exit count; they remain selectable in the table. Full stable IDs are in accessible marker labels/tooltips; unusually long tokens are abbreviated visually. At widths below 1150px, the passport moves below the hall instead of squeezing it. Long passports have their own scroll area.

Click a marker, table row or selection checkbox to open the same passport. It distinguishes recorded current assignments from eligible future activities, lists actual task completion times and unmet prerequisites, and shows accrued queue wait, preparation and service time separately. Completed visits show actual totals. Not-yet-arrived students have no elapsed visit time. Protected eligible waiters are explicitly labelled. Queue counts are not presented as fixed positions.

**No estimated remaining-visit time is shown.** The model's next-activity routing estimates are insufficient for a defensible full-visit prediction. The last recorded routing explanation remains available, including its actual numeric candidate estimates.

## Action semantics and determinism

Every accepted action has a stable ID, finite simulated timestamp, kind, JSON payload and a boundary flag. Legacy close/restore inputs receive deterministic IDs when accepted. Duplicate IDs and conflicting surge student IDs are rejected before mutation. Engine records expose immutable action tuples; payload access returns a new decoded object. Disruptions are included in the event feed, and success/errors appear in the panel and notifications.

* **Close/restore:** an active service finishes at its scheduled time. A closing desk accepts no new starts; after completion it is Closed. Restore reopens eligible dispatch. Paused actions apply at the current timestamp and do not advance the clock. Actions can change queue/service state at that timestamp, which is intentional.
* **Slowdown:** choose a service and set a multiplier from 1 to 3. Already-started service retains its effective duration. Future starts use `immutable base duration × current multiplier`; service-start events record both values. Selecting 2× twice remains 2×, not 4×. Setting 1× restores future starts. Routing uses multiplied own/queued work and the actual remaining times of active services. The scoring and tie-breaking policy are unchanged. Existing queue assignments are not reconsidered solely for a multiplier change.
* **Surge:** accept 1–30 students over 0–10 simulated minutes. The complete batch is generated before application using a private RNG seeded by SHA-256 of scenario seed and action ID. Arrival spacing is evenly distributed over the selected interval; each service duration, readiness and preparation duration is generated independently of the base generator. A single-student surge arrives immediately. IDs include the action ID. The full generated `StudentInput` records are serialized in the action payload and in the surge event; reruns consume them without drawing again. The original workload tuple stays unchanged. Bookkeeping includes injected students in arrival, completion and unfinished counts. Scheduled future surge actions prevent premature successful termination while pending.

The controller accepts disruptions only after Start and before completed/limit states; paused and stalled runs can accept them. A completed run requires Reset. Surge arrivals beyond the safety limit are rejected. A per-intent 700ms guard rejects rapid duplicate clicks without conflating different deliberate actions; engine duplicate-ID validation is the authoritative second layer. Wall time is used only for click rejection, never to calculate simulation results.

Priority ordering remains action 0, completion 1, arrival 2, dispatch 3 for scheduled input. UI actions include `at_boundary=true` and use priority 4 so preloaded action records occur **after** the timestamp's already-observed normal transitions. Their resulting zero-time arrivals/dispatch are processed before the next boundary action. This fixes the Phase 1 same-timestamp ordering gap for ordinary live controls, with regression coverage for identical events and metrics from the recorded action list.

Full interactive replay remains deferred. A live `run_stalled` diagnostic can differ from a rerun that already knows a future restoration, as noted in Phase 1. Future replay must capture observation checkpoints if those diagnostic observations must also match. Scheduled inputs and the tested boundary-action sequence reproduce exactly. No branching/replay UI is implemented.

## Congestion spotlight

The Python presenter considers services with waiting students. It ranks unavailable services first, then **effective queued service workload / number of open desks**, descending. Among unavailable services it uses queued work; stable service order breaks exact ties. Queued work includes current multipliers and excludes active service. Closed-but-finishing desks count as active but not open. Each insight shows queue size, oldest accrued current wait, serving/open counts and queued work.

The title is **Current congestion hotspot**, not a claim of a proven system bottleneck. Empty counter queues show No current congestion. Preparation is reported separately because it has no staffed resource in this model. The relevant zone gets a restrained amber border; it never flashes. Service unavailability is explained explicitly in Insights and desk states.

## Animation and session lifecycle

`presenters.py` derives all positions, counts, progress, task status, times and explanations in Python. `ui/hall.js` is a small NiceGUI Vue component: it renders SVG, emits selection and interpolates positions for 180ms. Marker nodes are keyed by student ID; the SVG is not replaced each frame. There is at most one animation-frame chain, cancelled on new data or component destruction.

Movement is illustrative and adds **no simulated travel time**. At 5×/20×, reduced-motion mode or an operating-system reduced-motion preference, markers snap to the latest authoritative positions. Pausing cancels movement and settles at the authoritative paused position; nothing continues drifting. Reset changes the generation, removes markers and selection, resets multipliers/actions and cancels pending interpolation. Display progress is always calculated from Python time, with no independent browser progress clock.

There is one 250ms client-bound playback timer per page. Reset never creates another timer. The headless controller isolates state, checks generations for stale ticks and rejects invalid controls. Rendering itself never advances the engine. A second browser page owns a separate controller. Client deletion cancels the timer; brief reconnects follow NiceGUI's normal lifecycle. No persistence across page reloads is promised.

## Honest baseline and engine changes

The unchanged demo still averages **23.368975 minutes Ordinary** and **27.550248 minutes QueuePact**. A regression test protects these outcomes. The obvious policy limitation is its local objective: shortest next activity, rather than shortest whole visit. Choosing photo first can defer verification and the payment work it unlocks. This is an explanation of the heuristic's limitation, not a causal proof for every minute of this workload's result.

Engine changes are limited to action validation/IDs, immutable surge payloads and population tracking, future-start multipliers, boundary action ordering, and start/finish timing in read-only counter snapshots. Policy rules, prerequisites, fairness and base workload generation are preserved. Presentation totals include partially elapsed preparation and effective active service, rather than incorrectly counting those intervals as waiting. The old invariant test helper now checks immutable inputs for both original and injected students.

## Two-minute presentation sequence

1. **0:00–0:20:** Start the default 40-student run. Explain the colors and that the policy is an experiment, not a waiting-time guarantee. Select a moving student and point out completed/eligible/current tasks.
2. **0:20–0:40:** Pause, open Disruptions and close a busy verification desk. Show Closing after current student. Add five arrivals over two minutes. Note the unchanged simulated timestamp.
3. **0:40–1:05:** Resume at 1× or 5×. Open Insights and explain the highlighted queue using its waiting count and queued work. Show the recorded disruption/decision feed.
4. **1:05–1:25:** Restore the desk. Optionally set photo capture to 1.5× and back to 1×, explaining future-start semantics.
5. **1:25–2:00:** Select 20×, observe completed visits and unfinished counts. Open a completed passport for actual totals. Finish by resetting to a clean run.

## Limits and scope

The heuristic is not globally optimal. Preparation remains unlimited self-service; the model knows base service requirements. Congestion is a current observation, not a forecast. Markers coalesce at high playback speeds and do not show every intermediate visual step. Full event history is retained in memory while rendered markers/feed are bounded; this is intended for college-scale scenarios, not an unbounded production session. Very large configured desk counts expand the headless hall model; the basic UI retains the established six-desk configuration.

No comparison races, staff placement experiments, branching replay, reports, authentication or cloud deployment were added.
