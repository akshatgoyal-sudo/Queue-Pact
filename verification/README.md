# QueuePact verification

## Scheduling diagnosis pass — 2026-09-08

Baseline **104 passed**, final **130 passed**. Initial sandbox pytest failures were filesystem permissions in existing temporary/cache directories; the authorized baseline rerun passed. Final checks used a fresh workspace test directory, and `pip check` / `compileall` passed. No simulation accounting or prerequisite/capacity correctness defect was found. Ordinary and legacy QueuePact event behaviour remain unchanged; no user database was overwritten or default storage location changed.

See [diagnosis and adoption decision](../docs/scheduling.md) and [predeclared protocol](../docs/scheduling-protocol.md). Development: 100 cases × four policies/candidates; held-out: 100 disjoint cases × three policies. All completed. V2 mean held-out queue wait 42.0016 min versus v1 40.8783 and Ordinary 36.9513. V2 remains experimental; defaults were not promoted. Original presets reproduce and now also include v2 outcomes in `scheduling/presets.csv`. Complete tables, paired differences, worst regressions and SVG charts are in `scheduling/`.

Browser verification executed with installed Chrome and a private `.local/scheduling-browser.sqlite3` database on a temporary server. Selected v2 in Live Operations, completed six students, paused/resumed/reset; saved and downloaded JSON, verified reconstruction and explicit policy version 2; opened a report with the experimental label; opened the saved input as an isolated working experiment and completed it; completed both v1-versus-v2 and Ordinary-versus-v2 comparisons with 40 students per panel. Screenshots were visually inspected at 1366×768 with no horizontal overflow. Captured console/page errors: zero. Test script completion assertions were corrected to target the status header after visual inspection caught an earlier false-positive match on the metric label. The corrected final pass verifies actual terminal status and zero unfinished students in the saved export. A transient hidden-select locator issue was also fixed in the test script, not suppressed in the application. Artifacts: `scheduling/browser/checks.json`, screenshots, report and JSON.

This focused pass did not repeat the entire Phase 4 print/offline/restart matrix or manually exercise every disruption with v2. Versioned reconstruction, surges/slowdowns/closures/staff additions, stepping invariants, CSV identity, legacy records, score explanations and accounting identities have automated regression coverage. The two-panel UI, report identity and live controls were browser-tested. New schemas are backward-compatible on read: legacy RunRecord 1 retains exact serialization, new RunRecord 2 records policy_version. The imported historical Phase 4 JSON still verifies. Policies and metrics remain in Python; no new dependency was added.


## Phase 4 verification — 2026-09-08

Baseline executed before edits: **80 passed**. Final suite: **104 passed**. `pip check` and `compileall` passed. Python 3.14.3, NiceGUI 3.16.0, SimPy 4.1.2 and Plotly 6.9.0; optional browser verification versions are pinned in `verification/requirements.txt`.

Implemented SQLite history, immutable save/export captures, validated JSON import and explicit reconstruction verification, CSV ZIP downloads, offline HTML reports with browser printing, three deterministic presets, guided presentation and source-relative launcher. No scheduling policy or original demo workload was changed. Regression tests cover persistence/restart/concurrency, isolated loaded copies, schema/content rejection, precision, CSV quoting/formula safety, frozen observations, tampered evidence detection, all experiment report types and preset reconstruction. Empty hall initialization and hidden Plotly resize handling were corrected after real browser console errors were observed; the final browser pass contains no captured console errors. Event findings scanning was made linear without changing findings or simulation decisions.

### Executed browser and print checks

`verification/browser_phase4.py` launches its own local server and installed Chrome, then terminates only that server. It exercises live start/pause, selection, presentation/fullscreen-or-supported-fallback, all preset loads and repeated resets; saves a live observation; downloads and inspects actual CSV/JSON; completes comparison, staffing, candidate continuation, unchanged reconstruction and readiness workflows; imports JSON and explicitly verifies reconstruction; restarts the server and reloads persisted evidence into a working copy isolated from another browser session. Screenshots and page widths were checked at 1366×768 and 1920×1080. The final capture reports no console/page errors and no external asset requests. External web requests were blocked throughout fresh page loads: local fonts/icons/halls/Plotly/report assets worked with loopback access only. This is browser network isolation, not a physical disconnected-network test.

Seven reports, covering every experiment type plus the three presets, were printed through Chromium's A4 PDF renderer. Every page has text, A4 dimensions and no print toolbar. Rendered pages were visually inspected for tables, charts, page breaks and clipping. Print spacing was tightened after detecting sparse trailing pages. The native Windows print dialog and physical printer were not automated; the application's button invokes the browser print workflow, not a direct PDF export service.

Artifacts: `phase4-browser/checks.json`, screenshots, downloaded ZIP/JSON and printed/rasterized QA pages; `phase4-results.json` contains unrounded headless outcomes. QA databases live under ignored `.local/`; normal storage defaults to `%LOCALAPPDATA%\QueuePact\queuepact.sqlite3`. Saved history is shared intentionally; mutable simulations remain isolated. See `docs/phase4.md` for override, backup, exact commands and presentation scripts.

| Prepared scenario | Completed, each policy | Ordinary average wait (min) | QueuePact average wait (min) | Ordinary / QueuePact makespan (min) |
|---|---:|---:|---:|---:|
| Normal Admission Morning | 40 | 23.37 | 27.55 | 86.47 / 87.22 |
| Arrival Rush | 50 | 35.09 | 44.92 | 109.40 / 113.57 |
| Desk Disruption and Recovery | 40 | 24.82 | 31.12 | 88.43 / 92.27 |

All six runs finished with zero unfinished students. No favourable seed search was performed; all presets use seed 42 and preserve the original base workload. Surge and closure/recovery actions are explicit. These measured outcomes support a discussion of coordination trade-offs, not a claim of guaranteed improvement. The tested workflows support a local college demonstration; production readiness is not claimed.


## Phase 3 verification — 2026-09-07 to 2026-09-08

Inspected the repository, ancestor instruction locations, README, `docs/phase2.md`, verification notes and relevant source before edits. No applicable AGENTS.md was found. Existing work was preserved. Baseline: **53 passed in 0.34 s**. Final expanded suite: **80 passed in 0.81 s**. `pip check` reported no broken requirements; `compileall` passed. The entire project remains untracked in the existing repository; no commit was fabricated and `git diff --check` is not treated as coverage of untracked files.

New tests cover immutable identical paired inputs/actions, independent headless equivalence, event budgets and playback invariance, future surges, fixed-horizon unfinished wait including blocked queues, frozen completed utilization windows, zero-reference handling, deterministic chart data, qualifications/spare desks, one additional worker, source isolation, ranking/ties, reconstruction and JSON, unchanged continuation, additive same-time ordering, surge uniqueness, operational readiness overhead/failed checks/preparation, readiness reconstruction, cancellation/reset/stale generation tokens, session isolation, no-feasible presentation, and existing prerequisites/capacity under disruptions.

The default headless commands were executed on the same workload for both policies. Raw outputs are in `phase3-demo/`; `verify_phase3.py` also produced `phase3-results.json` covering comparisons, staffing, readiness and unchanged branches. Both policies complete 40 visits. Ordinary average queue wait **23.368975**, QueuePact **27.550248**, a **4.181273-minute increase**. Makespans are 86.474101 and 87.223683. The recorded photo-first counts are 0 and 22. No policy or demo tuning was performed. See `docs/phase3.md` for the observation/interpretation distinction.

The unchanged default staffing trial at minute 0 through minute 60 selected photo capture: 29 completed, 702.90 accrued waiting minutes, versus reference 25 completed and 844.65 minutes. This is best among these tested placements for the stated objective, not a universal recommendation.

### Browser checks actually performed

Used the in-app browser against locally launched NiceGUI builds and then a clean final server on port 8080.

* Started the normal paired run; paused at common boundaries, resumed and selected 20× playback. Run to results was exercised on the default comparison and readiness trials. Completed demo cards showed 23.37/27.55 and 40/40, with separate frozen completion windows.
* Visually inspected compact halls, queue overflow counts, unfinished metric populations, measured findings, completion and queue charts. Measured viewport/page widths were **1366/1351** at 768 height and **1920/1905** at 1080 height (the difference is the scrollbar); no horizontal page overflow. Settings now collapse on start so primary controls and hall fit more usefully. Screenshot rendering at large size is scaled by the browser capture surface; layout was also checked through rendered DOM dimensions.
* Applied a shared 1.5× verification slowdown at a paused 20.00-minute boundary; both halls displayed it. In the final build, added a five-student shared surge at 21.25 minutes. Two rapid clicks accepted `shared-1` once and displayed “This action was just accepted” for the second; the clock remained paused.
* Ran all feasible staff trials, inspected all reference/candidate rows and opened the selected candidate branch. A trial with all qualifications deselected produced a readable no-feasible explanation, reference-only results and disabled candidate opening.
* Reconstructed unchanged continuations at minute 10. Branched the original Ordinary source at minute 10 with a 1.5× verification multiplier: unchanged average wait remained 23.37, intervention wait was 29.44; both finished 40. Inspected the turning-point controls and action timeline.
* Ran readiness comparison to completion. Early: 40 completed, 23.31 average wait, 20.00 screening worker-minutes. Late: 40 completed, 22.81 average wait, 7.50 failed-check desk-minutes. Both showed 51.88 preparation minutes and zero unfinished.
* Cancelled Run to results on a 1000-student trial; observed Cancelled at 51.25 minutes, then reset. A second lab remained Ready/0.00, while a separate Live Operations page remained independently paused at 5.50. Verified Live Start, Pause and table selection opening a student passport.
* Reset and started again; source records, results and markers cleared. Corrected stale headings/empty SVG artifacts discovered in reset inspection. One timer is retained per client; headless controller tests check stale callbacks and duplicate-job rejection.
* Inspected server stdout after interactions: no server exceptions. No visible application-error banners were observed. Full DevTools console capture was not available through the selected browser surface, so no claim of a complete console audit is made. Not every intervention type was manually repeated in every experiment; closure, restore, multiplier, staffing and surge semantics also have automated regression coverage.

Temporary test servers were stopped; the final current build is left on `http://127.0.0.1:8080/lab`. Python 3.14.3, NiceGUI 3.16.0, SimPy 4.1.2, pytest 9.1.1, Plotly 6.9.0 and its narwhals 2.25.0 dependency were tested. Plotly is locally served through NiceGUI; no separate frontend application or paid service was introduced.

During the final restart, Windows `Stop-Process` failed and two launch attempts encountered the still-occupied port. The identified old QueuePact listener was terminated with approval using `taskkill`; the final launch then bound successfully and the clean Lab page was opened again. These were resolved restart issues, not simulation test failures.

### Correctness and scope notes

Default routing/dispatch rules and demo inputs are unchanged. Added engine hooks enable explicit readiness attempt handling, and a validated `add_staff` action adds one resource. New resource close/restore actions are rejected if scheduled before its creation. Experiment fixed-horizon observations include blocked waiting and known future surge populations; replay normalization excludes polling-dependent stall diagnostics only. These are experiment accounting/validation additions, not an optimization of either policy.

Known limitations and the short demo sequence are in `docs/phase3.md`. Histories are in memory; setup cancellation discards bounded worker-thread results rather than forcibly killing threads. Final reports, history import/export UI and presentation packaging remain Phase 4.

## Phase 2 verification — 2026-09-07

The existing repository, README, these notes and applicable instruction locations were inspected before edits. No AGENTS.md was present. The baseline suite was executed and confirmed **39 passed**. The final expanded suite is **53 passed** (0.47 seconds in the final regression run); `pip check` reported no broken requirements and `compileall` passed. A later sandboxed pytest invocation hit the previously seen Windows temporary-directory permission issue; rerunning with approval passed all tests.

New tests exercise hall counts/closing/progress and bounded markers, passport prerequisites and actual time accounting, future-only slowdown and 1× restoration, immutable and deterministic surge inputs, unique/duplicate IDs, dynamic completion bookkeeping, scheduling invariants with both policies under disruptions, congestion ties and unavailable desks, presenter read-only behavior, controller isolation/reset/stale ticks, rapid-click protection, boundary-action reproduction and unchanged baseline averages.

Both policies were rerun headlessly with the same demo workload; current outputs are preserved in `phase2-demo/`. Results remain exactly the Phase 1 values shown below: Ordinary **23.368975 min** and QueuePact **27.550248 min** average completed queue wait, with 40/40 completed under both. No routing policy optimization or input changes were made.

### Browser checks actually performed

* Loaded the new NiceGUI page and persistent SVG hall.
* Started the normal 40-student run, paused at 0.25 min, selected S0001 from the hall, and inspected its current assignment, prerequisites, times and recorded routing decision.
* While paused, closed busy V1, set verification to 1.5× duration, and added five arrivals over two minutes. All three actions had timestamp 0.25 min. Rapid double-clicking the surge button accepted A0003 once and displayed a rejection for the repeat; the population became 45, not 50.
* Resumed and observed V1 change from Closing with S0001 to Closed after its scheduled service. Paused at 50.50 min with 33 waiting: the hall showed seven queue markers plus **+26 waiting**, and verification was highlighted as the congestion hotspot.
* Restored V1 and set verification back to 1×. Inspected actual action descriptions using the Disruptions event filter.
* Selected S0002 from the directory checkbox and viewed its completed passport: actual wait, service and visit times plus each completion timestamp. Found and fixed direct row-click event arguments; direct cell/row selection then opened S0002's passport as well.
* Switched to 20× and observed **45/45 completed at 124.11 simulated minutes**, zero unfinished. Reset cleared markers, selection, actions and clock. Repeated Start/Pause/Reset with the corrected final app.
* Confirmed a second page remained Ready at 0.00 while the first page was Paused at 0.25; closed the extra page afterward.
* After Reset, selected QueuePact with six students and 20× playback. The repeated run completed **6/6 at 20.76 min**, with zero unfinished and empty browser warning/error logs.
* Exercised Reduced motion. Paused marker coordinates and clock remained fixed between observations. High-speed playback snapped to current positions rather than retaining motion trails.
* Inspected at **1366×768** and **1920×1080**. DOM viewport measurements reported document widths of 1351 and 1905 respectively (scrollbar excluded), with no horizontal page overflow. The final layout keeps primary controls above the hall, places long details below, and bounds passport scrolling. Inspected screenshots and element bounds; the in-app browser's full-page stitch at the larger override produced duplicate/cropped screenshot strips, so that stitched artifact is not treated as evidence of page overflow. Normal viewport inspection and DOM bounds were used instead.
* Browser warning/error logs for the working page were empty. The working server produced no interaction errors. Temporary servers were replaced by one final loopback server on port 8080.

### Fixes made during this phase

* Explicit UTF-8 CSS loading fixes an observed Windows page-startup decode error.
* Direct table-row event wiring now sends only the row ID, following NiceGUI's generic event API.
* Live actions record boundary ordering, closing the Phase 1 same-timestamp ordering gap for the tested control sequence. Full branching replay and exact reproduction of prior stalled observations remain deferred.
* Future-start durations and effective queued work use service multipliers; active service timing stays fixed. This is the requested action semantics, not a redesigned scheduling heuristic.
* The invariant helper now includes immutable inputs from injected students; otherwise it incorrectly treated document-ready surge students as unprepared.

See `../docs/phase2.md` for exact launch commands, semantics, limitations and the two-minute presentation sequence.

---

## Preserved Phase 1 verification

Executed on 2026-09-07, Windows, Python 3.14.3. Dependency versions are recorded in `../requirements-tested.txt`.

## Automated and headless checks

* Full pytest suite: **39 passed**, including 10 varied-seed/policy disruption runs checked after every calendar event.
* `pip check`: **No broken requirements found**.
* `git diff --check`: no whitespace errors reported.
* Editable package installed successfully; both `python -m queuepact` modes launched successfully.
* The first test fixture did not create its intended fairness queue; it was corrected to account for the actual routing score and stable ID order. The final fairness test demonstrates a real order reversal after closure-driven reassignment.
* Windows blocked pytest's temporary directory on a subsequent sandboxed run; the suite was rerun with filesystem approval and passed. A missing setuptools backend in the new venv was resolved through normal editable installation with build isolation.

Demo (`examples/demo.json`), **one generated workload shared by both policies**:

| Policy | Status | Completed | Unfinished | Finish time | Mean queue wait | P90 queue wait | Mean visit |
|---|---|---:|---:|---:|---:|---:|---:|
| Ordinary | Completed | 40 | 0 | 86.4741 | 23.3690 | 35.8808 | 34.5397 |
| QueuePact | Completed | 40 | 0 | 87.2237 | 27.5502 | 39.6145 | 38.7210 |

All time values are simulated minutes. QueuePact has **higher waiting time in this demo**; the heuristic is not guaranteed to improve every workload. No improvement percentage is assumed or hard-coded.

The additional headless disruption run used `examples/actions.json` (photo closed at 5, restored at 15). Both policies completed all 40 students with zero unfinished. Full authoritative output is in `disruption/summary.json`.

`demo/` and `disruption/` contain the workload/action inputs, each policy's structured event JSON and its metrics summary.

## Browser verification actually performed

The local NiceGUI interface was exercised through the available in-app browser:

* Initial Ready state and zero clock displayed.
* Mouse Start advanced the clock and locked configuration.
* Mouse Pause displayed Paused; Resume restarted playback.
* Closed a busy verification desk: it displayed Closed while retaining its active student.
* Restored that desk and resumed the run.
* Reset during playback returned to Ready, zero time, empty event feed and open desks; configuration unlocked.
* Selected QueuePact, changed count to six, selected 20× playback, and ran to **Completed at 20.76 minutes**, six completed and zero unfinished.
* Reset again returned the smart run to Ready at zero.
* A second browser page remained at its own Ready/zero-clock state while the first page ran; it was closed after verification.
* Visual inspection confirmed the light background, dark header, labelled controls, colored metrics and counter cards. The in-app browser uses a narrow panel, where cards wrap.

An initial live-refresh implementation recreated counter elements and could shift the page under mouse clicks. This was fixed by retaining counter controls and updating their text; the mouse control sequence passed afterward.

The headless tests cover exact busy-close completion timing, capacity restoration, timer-independent stepping outcomes and fresh engine state. Browser verification is a manual exercised sequence, not a claim of an automated cross-browser test matrix.
