# Phase 4: local persistence, evidence and presentation

QueuePact is **queue coordination and decision testing for college admissions**. It is a local educational prototype, not a production admissions system or a promise of shorter queues.

## Project overview

Students must visit several counters with prerequisites, shared capacity and occasional document problems. Teachers, students and admission coordinators can use this simulation to inspect how task order, document readiness and disruptions affect waiting and completion. The implemented solution combines a live admission hall, student passports, measured comparisons, staffing trials, reconstructable branches and explicit readiness alternatives.

The project is predominantly Python: dataclasses/enums define the domain; SimPy schedules events; Python implements routing, fairness, workload generation, metrics, experiments, SQLite access, export validation and report content. NiceGUI builds the UI from Python. Small JavaScript components only render/interpolate SVG, lay out Plotly charts, select students and invoke browser presentation features. They do not schedule services or fabricate results.

## Install and launch in PowerShell

```powershell
Set-Location 'C:\Users\KIIT0001\OneDrive\Documents\ChatGPT\QueuePact'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-tested.txt
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m queuepact headless --scenario examples/demo.json --policy both
.\.venv\Scripts\python.exe -m queuepact ui --port 8080
```

Alternatively, `powershell -ExecutionPolicy Bypass -File .\Start-QueuePact.ps1 -Port 8080` resolves the project and virtual environment relative to the script. This process-only invocation does not change the machine execution policy. The launcher checks dependencies, never installs packages automatically, never kills another listener, and prints useful errors. Use a different `-Port` when occupied.

Open `/` for Live Operations, `/lab` for Comparison Lab and `/history` for saved evidence. Installation initially requires package access. Normal operation requires a browser and the local Python server, but no internet connection, CDN, account or paid service. NiceGUI serves its font/icon files and Plotly JavaScript locally; the application uses installed system fonts and inline SVG. Reports contain inline CSS and SVG and no external assets.

Optional repeatable browser/print verification requires installed Chrome and additional **test-only** tools:

```powershell
.\.venv\Scripts\python.exe -m pip install -r verification\requirements.txt
.\.venv\Scripts\python.exe verification\verify_phase4.py
.\.venv\Scripts\python.exe verification\browser_phase4.py
```

The browser script owns a temporary server on 8091, uses a fresh Chrome context, blocks all non-local web requests, exercises downloads/import/restart, and prints verification PDFs. It stops only its own child server. These tools are not runtime dependencies or a new PDF export feature.

## Storage, sharing and backups

Default Windows database: `%LOCALAPPDATA%\QueuePact\queuepact.sqlite3` (normally `C:\Users\KIIT0001\AppData\Local\QueuePact\queuepact.sqlite3`). This location is independent of the current working directory. To override, supply an **absolute** path:

```powershell
$env:QUEUEPACT_DB = 'C:\Users\KIIT0001\OneDrive\Documents\ChatGPT\QueuePact\.local\demo.sqlite3'
.\.venv\Scripts\python.exe -m queuepact ui --port 8087
# Or pass -Database with the absolute path to Start-QueuePact.ps1.
```

Saved records are shared across browser sessions for this single-operator prototype. Mutable engines, playback, selection and experiment jobs remain isolated. Opening a saved record creates new engines from its recorded inputs; it does not mutate the historical result or another page. Save is explicit, never per animation frame.

The SQLite repository uses parameterized statements, short independent connections, transactions, a busy timeout and foreign keys. Records are append-only, with UUIDs, UTC capture time, experiment type, name, status, configuration/workload, actions/surge inputs, horizon, assumptions, summaries, parent reference and version information. Scenario copies use the same envelope with kind Scenario. Renaming/editing a working scenario creates a new save; no completed evidence is overwritten. Branches based on a saved/captured source retain its parent record ID. Unsaved sources naturally have no persisted parent until saved.

History shows the newest 500 records; it does not delete older ones. In-memory working-source lists remain bounded to 12. No authentication or deletion workflow was added.

For a simple backup, stop the application, copy the `.sqlite3` file to a safe location, then restart. For an online consistent backup, use the repository's SQLite backup API:

```powershell
.\.venv\Scripts\python.exe -c "from queuepact.repository import Repository; Repository().backup(r'C:\Users\KIIT0001\Documents\QueuePact-backup.sqlite3')"
```

Restore only with the app stopped, keeping the original backup. Prefer a local disk for the active database; use synchronized folders for closed backups rather than assuming a sync client provides database concurrency guarantees. The verification databases and demo handoff database are under `.local/`, ignored by git.

## Save, export, import and verify

1. In Live Operations or the Lab, click **Save / export**. A synchronous capture freezes a consistent observation; it neither advances nor reruns the engine. Partial event boundaries must settle first.
2. Name it. **Save snapshot** appends evidence to SQLite. **Save scenario copy** saves initial inputs for a fresh scenario, not running generators.
3. **Download CSV ZIP** and **Reproducibility JSON** use the same frozen observation even if playback continues. **Capture again** explicitly replaces that transient capture. Editing the saved name creates a new saved copy.
4. **View report** saves the captured evidence and opens an HTML report. Use **Print / Save as PDF** in the browser. It is never labelled as a direct Python-generated PDF download.
5. In History, select a row to view results, export, open a new working experiment, or **Verify reconstruction**. The latter is an explicit background rerun that checks metrics, normalized event digest, student outcomes, resource state, overhead, chart series and derived findings. Historical viewing alone is not a successful reproduction test.
6. Import a QueuePact JSON file through History. The importer validates schema, engine compatibility, size, model constraints and fingerprints, ignores no executable instructions, accepts no filesystem paths, and creates a new saved copy. Imported historical metrics remain unverified until reconstruction matches. Result tampering can remain viewable as historical data but fails verification.

Reports prominently label incomplete, horizon-limited, blocked or cancelled observations, with each run's own time window and population. Ready scenario records are inputs, not completed evidence. Full-precision numbers remain in JSON/SQLite; display rounding is only for readability. Known future surge students count as unfinished before arrival. Completed-only means, nearest-rank p90 and maximum wait must be read alongside unfinished counts and all-student accumulated waiting.

CSV ZIP contains metrics, student outcomes, action history and resources; staffing captures also contain candidate outcomes. Files use UTF-8 with a BOM, standard CSV quoting, explicit units, and empty cells for undefined values. Numeric values are not rounded. Potential spreadsheet formulas in user text are prefixed with an apostrophe; negative numeric values remain numbers. JSON is lossless for the recorded Python float values and preserves generated surge payloads.

Schema 1 and `queuepact-engine-1` are checked before reconstruction. Runtime versions are recorded with new evidence. JSON is limited to 10 MB, five constituent runs, 1000 base students and 100 actions per run. Existing lab resource/time limits still apply. No pickle, live generator serialization or arbitrary historical snapshot loading is used. Integral timestamp representations such as `10` and `10.0` normalize only for semantic hashing, not by rounding simulation data.

## Architecture

```text
Scenario + private seeded RNG → immutable StudentInput workload
                           ↓
Policy + actions → isolated SimPy Engine → events + snapshots + metrics
                           ↓
              PairedRun / staffing / readiness / reconstruction
                           ↓
Python presenters → NiceGUI live UI and Comparison Lab
                           ↓ explicit capture
Immutable Evidence JSON → SQLite Repository (append-only, parent IDs)
                           ↓
                 CSV ZIP / reproducibility JSON / HTML + inline SVG
                           ↓
                 browser print workflow → user-selected PDF/printer
```

New modules: `archive.py` (capture/validation), `repository.py` (SQLite), `exports.py` (CSV ZIP), `reports.py` (HTML/print SVG), `presets.py`, `ui/history.py`, `ui/presentation.py`, and `ui/responsive_plot.*`. Plotly's hidden-container resize issue is addressed by a renderer that waits for a visible connected container, not by hiding console errors. Empty hall models always provide finite geometry.

## Actual algorithms and assumptions

Ordinary uses preparation first when needed, then verification → photo → payment → enrollment, with FCFS shared service queues and every available compatible desk. QueuePact chooses among eligible unfinished tasks using:

`estimated next completion = own effective duration + (queued effective work + remaining open-desk work) / open desks`

No open desk makes that service estimate unavailable. Preparation competes as its known duration; deterministic service order breaks score ties. Routing normally occurs after an activity, not on every refresh. Fair-wait protection uses the configured waiting-age threshold within the eligible service queue, oldest protected wait first. It cannot bypass prerequisites or create capacity, and does not guarantee a maximum wait.

The private seeded RNG generates arrivals, all service requirements, readiness flags and preparation durations before either policy runs. Surges use an action-specific generator and record their full generated inputs. Reconstruction reruns these inputs and ordered actions through the original inclusive boundary; new branch actions follow the original same-time events. `run_stalled` polling diagnostics alone are omitted from normalized event comparisons.

QueuePact optimizes the estimated **next activity**, not the whole visit. Moving students to photo early can alter downstream demand. The original demo has 22 photo-first QueuePact students versus zero Ordinary, but that association is not proof of a specific causal mechanism. It is entirely possible for QueuePact to perform worse. No policies or seeds were tuned in this phase.

Preparation is an unstaffed timed activity. Early screening explicitly adds staffed screening time; late discovery occupies verification for failed attempts and requeues after preparation. Staffing candidates add one qualified worker at one spare desk with no training/setup/travel cost. These simplifications are documented simulation assumptions, not real-world validation.

## Prepared scenarios and observations

All use seed 42 and the original base workload/resources; the original demo remains Normal Admission Morning.

| Preset | Real scheduled difference | Completed, both | Avg wait Ordinary / QueuePact | Makespan Ordinary / QueuePact |
|---|---|---:|---:|---:|
| Normal Admission Morning | None | 40 | 23.37 / 27.55 | 86.47 / 87.22 |
| Arrival Rush | 10 arrivals during minutes 12–14 | 50 | 35.09 / 44.92 | 109.40 / 113.57 |
| Desk Disruption and Recovery | V1 closes at 10, restores at 25 | 40 | 24.82 / 31.12 | 88.43 / 92.27 |

All durations are simulated minutes. Observe extra unfinished students and congestion during the rush, and reduced capacity/recovery during closure. Both policies finish each preset, but QueuePact's average wait is higher in all three. These are measured examples, not universally representative estimates.

## Two-minute presentation

1. Open Live Operations → Prepared demos & presentation mode. Choose **Desk Disruption and Recovery**, Start demo, then Presentation mode. Explain the four tasks and prerequisites using the caption.
2. Pause and Follow student. Point to separate wait, preparation and service values. Resume to observe V1 closing at 10 and restoring at 25. At 5× these actions occur within a few real seconds; pause to discuss them.
3. Exit presentation → Open preset comparison. In the new Lab tab choose Run to results. Read **24.82 versus 31.12** average completed wait and both 40 completions. Explain that the heuristic is not a guaranteed improvement.
4. Save / export → give a name → Save snapshot → View report. Point out the population labels and reproducibility footer; Print / Save as PDF uses the browser.

## Five-minute presentation

1. Start Normal Admission Morning, pause, follow a student, and explain verification/payment/enrollment prerequisites and independent photo eligibility.
2. Exit presentation and choose Arrival Rush → Load preset → **Replace with preset**. Unsaved working progress is explicitly replaced. Start demo, observe the ten generated arrivals at minutes 12–14, pause, and inspect the congestion indicator. Move captions backward/forward to show that captions do not apply interventions.
3. Reset Demo; demonstrate that time/selection/actions restart but saved history survives. Choose Desk Disruption and Recovery, confirm replacement, and show closing → closed → restored using actual scheduled actions.
4. Open Normal's preset comparison and Run to results: both finish 40, average wait **23.37/27.55**. In Extra staff, use the Ordinary source and the 60-minute end time; test all qualified placements. The unchanged base trial selects photo: **29 completed**, versus **25** for reference, for the stated objective.
5. Show History and open a saved run as a new experiment. Verify reconstruction explicitly. Show the report and JSON/CSV choices, then state limitations and distinguish simulation evidence from deployment claims.

## Viva: ten concise answers

1. **Why Python?** It handles our domain, algorithms, simulation, metrics, experiments, database and UI orchestration in one language; browser code only renders.
2. **Why SimPy?** Discrete events model arrivals and service completions without wasting simulated time on frame-by-frame polling.
3. **Wait versus visit time?** Queue wait is time waiting for an activity resource; visit time also includes preparation, screening where applicable, and service.
4. **How are prerequisites enforced?** Eligibility checks precede routing/dispatch, and completion sets unlock later tasks. Failed document checks do not complete verification.
5. **What does fairness mean?** Eligible students beyond a wait threshold receive protected priority within their service queue; insufficient capacity can still cause long waits.
6. **What makes results deterministic?** Immutable pre-generated workloads, recorded surge payloads, stable IDs/ties and a documented same-timestamp event order.
7. **How does replay work?** We reconstruct from inputs and actions; we do not pickle running SimPy generators. Unchanged continuations are checked against authoritative results/events.
8. **Is the policy comparison fair?** Both receive identical exogenous inputs/resources/actions. Readiness screening adds workers and is explicitly a different operational comparison.
9. **Why can QueuePact lose?** Its local next-task score does not optimize downstream visit completion, so task ordering can worsen queueing trade-offs.
10. **What remains before real-world use?** Calibrated data, operational validation, privacy/security, multi-user controls, institution-specific constraints and careful integration. None is claimed implemented here.

## Readiness and limitations

The demonstrated source-based workflows are suitable for a local college demonstration in the tested environment. This is not production-ready. Native print-dialog options and fullscreen depend on the browser/host; reports were verified with Chromium's A4 print renderer, while fullscreen offers a readable fallback when unsupported. Offline verification blocks external web requests, not the required loopback connection. Reproducibility across arbitrary future Python/library versions is not promised. Saved history has no authentication and is intentionally shared for one operator. No machine learning, new scheduling policies, cloud deployment or packaged executable was added.
