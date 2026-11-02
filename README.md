# VendorGate — Vendor onboarding, from submission to approval

Zamp ASA case study · **PS-2 (Operations)**.

A vendor submits a form and PDF documents. An 11-stage process validates, cross-references and verifies everything, then produces a clear status with the reasoning visible:

| Status | Meaning | What the vendor receives |
|---|---|---|
| **Approved** | Every check passed; a vendor code is issued and the vendor is added to the vendor master | Welcome email with the vendor code |
| **Pending · awaiting vendor** | Things only the vendor can fix (missing field, wrong document, typo in GSTIN…) | One consolidated, numbered list of fixes plus a secure link to a resubmission portal |
| **Pending · internal review** | Risk signals a human must judge (bank account in someone else's name, sanctions near-match, reused tax ID) | A neutral "under review" email (fraud signals are never disclosed); the review team gets an internal alert with the evidence |
| **Rejected** | Disqualifying (GST cancelled, company struck off, exact duplicate of an existing vendor) | Rejection email with the reason, where the reason is safe to disclose |

The whole thing runs **offline on localhost**. An LLM is optional. If an OpenAI or Anthropic key is present it helps read documents and writes friendlier email greetings, but **it never decides a status**.

---

## Run it

### Windows

Requirements: Python 3.9 to 3.14 from [python.org](https://www.python.org/downloads/windows/). Tick **Add python.exe to PATH** in the installer. On an ARM (Snapdragon) laptop, use Python 3.11 or newer. Node.js is not needed, because the zip ships the built UI in `frontend/dist`.

1. Right-click the zip and choose **Extract All**. Scripts cannot run from inside a zip.
2. Double-click **`start.bat`**. The first run installs the Python packages into `backend\.venv`, which takes about a minute and needs internet. Later runs work offline.
3. The browser opens http://localhost:8000 by itself. Press **Ctrl+C** in the console window to stop.

From a terminal you can pass options: `start.bat --port 8010` or `start.bat --no-browser`. Double-click **`run-tests.bat`** to run the test suite. If Windows SmartScreen warns about the script, choose **More info**, then **Run anyway**.

### macOS / Linux

Requirements: Python 3.9+. Node 18+ is needed only when `frontend/dist` is missing, as in a fresh git clone.

```bash
cd vendor-onboarding
./start.sh            # first run installs deps, generates demo PDFs, builds the UI if needed
open http://localhost:8000
```

Both scripts call the same launcher, `run.py`, which uses only the standard library and can also be run directly with `python run.py`. It is idempotent. It creates `backend/.venv` and installs the pinned packages (skipped when `requirements.txt` hasn't changed). It then regenerates the scenario PDFs, which carry dates relative to today, builds the UI only if `frontend/dist` is missing, and serves everything from FastAPI on port 8000. Use `--port 9000` or `PORT=9000` to change the port.

Developer mode, with hot reload on both sides:

```bash
./dev.sh              # API on :8000 (reload) + Vite on http://localhost:5173
```

Tests:

```bash
python run.py --test       # 27 tests: validators + every scenario end-to-end (Windows: run-tests.bat)
```

### Optional AI assist

```bash
cp .env.example .env    # then set OPENAI_API_KEY or ANTHROPIC_API_KEY
```

The sidebar badge shows the active mode, either **Rules only** or **AI assist · provider**. Set `VO_LLM_PROVIDER=none` to force offline mode.

---

## Using the app

| Page | What it's for |
|---|---|
| **Dashboard** | Every submission with its status, risk and reason; KPIs (straight-through rate, average run time, top issues); **Reset demo data** |
| **New submission** | The vendor form and document slots. **Demo scenarios** on the right: *Load* fills the form so you can inspect it, *Run* submits immediately |
| **Submission detail** | Decision banner, a **live run view** (11 stages streaming in real time, each finding with expandable evidence), reviewer panel, and tabs for Summary, Documents, Messages, Versions and Audit trail |
| **Review queue** | Cases waiting for a human, highest risk first |
| **Outbox** | Every email the process drafted (vendor and internal) |
| **Vendor master** | The "ERP" vendor list that duplicates are checked against; approvals are added here |
| **How it works** | The process map and decision rules in plain language |
| **Vendor portal** (`/portal/<token>`) | What the vendor sees: their status, exactly what to fix (fields and document slots highlighted), resubmit |

**UI notes.** An editorial look: warm paper tones, serif headings (Newsreader) over Inter body text, a single forest-green accent and flat two-tone illustrations. All colours are CSS variables in `frontend/src/styles.css`, so light and dark themes share every rule. Light and dark themes (toggle at the bottom of the sidebar, or the top bar on mobile; the choice is remembered). The dashboard's status donut and KPI cards filter the table on click. In the live run view, click any node in the pipeline strip to jump to that stage. Documents can be dragged onto their slot. Empty and loading states use looping animated SVG scenes. Page and list entrances are CSS keyframes, which run on wall-clock time, so content never waits on a throttled animation loop (an unfocused window or an embedded preview pane). Framer Motion is used only for interactive motion such as the sliding tab and filter highlights. All motion switches off when the OS "reduce motion" setting is on.

---

## Architecture

```
React (Vite, TypeScript)  ──/api──►  FastAPI  ──►  Pipeline (thread pool, 11 stages)
        ▲                               │                 │
        └──── Server-Sent Events ◄──────┤                 ├─► Validators (GSTIN checksum, PAN, IFSC, CIN…)
              (live run view)           │                 ├─► Document reader (pypdf + regex, optional LLM)
                                        │                 ├─► Mock services (GST portal, MCA, IFSC, penny-drop, sanctions)
                                        ▼                 ├─► Vendor master (duplicates)
                                     SQLite (WAL)  ◄──────┴─► Messaging (outbox) + audit log
```

- **Pipeline:** `backend/app/pipeline.py`. Every stage always runs, so the vendor gets one complete list of fixes. Each finding records a severity (pass, info, warn or fail), a **resolution owner** (vendor, review or reject), a vendor-facing action, a hint, a risk weight and evidence. The decision stage applies fixed precedence rules to those findings (see `docs/DESIGN.md`).
- **Live view:** each stage and finding is written to `run_events` and streamed over SSE (`/api/runs/{id}/events`, with resume via `Last-Event-ID`).
- **Fail-closed:** if a stage crashes, a `SYSTEM_ERROR` finding routes the case to human review. Runs interrupted by a restart are marked failed and routed to review.
- **External services are mocked** with seeded, fictional datasets in `backend/app/seed/`. Each mock is one class with a `lookup` or `verify` method, which is the seam where a real API client slots in.

### Project layout

```
vendor-onboarding/
├── start.bat / run-tests.bat   Windows launchers (double-click)
├── start.sh / dev.sh / .env.example
├── run.py                 cross-platform launcher both start scripts use
├── backend/
│   ├── app/
│   │   ├── main.py            API routes, SSE, file upload, SPA serving
│   │   ├── pipeline.py        the 11-stage process + decision rules
│   │   ├── validators/india.py GSTIN (mod-36 checksum), PAN, IFSC, CIN, LLPIN, Udyam, phone, PIN…
│   │   ├── matching.py        company-name normalisation + fuzzy match (Pvt Ltd ≡ Private Limited)
│   │   ├── documents.py       PDF text extraction, content classifier, field parsers, LLM fallback
│   │   ├── mock_services.py   GST portal, MCA, IFSC directory, penny-drop, sanctions screening
│   │   ├── messaging.py       vendor + internal email drafting (templated; LLM only for greeting)
│   │   ├── llm.py             OpenAI / Anthropic via httpx, auto-detected, never raises
│   │   ├── repository.py      all SQL
│   │   ├── db.py / config.py / models.py
│   │   └── seed/*.json        mock registries, banks, watchlist, existing vendors
│   ├── scripts/generate_samples.py   renders the scenario PDFs (reportlab)
│   ├── sample_data/           generated scenarios + scenarios.json
│   └── tests/                 validators + end-to-end scenario tests
├── frontend/src/              React app (pages/, components/, api.ts, lib.tsx, styles.css)
└── docs/
    ├── DESIGN.md              process map, rules, assumptions, edge cases, roadmap
    ├── DEMO_SCRIPT.md         live demo + 5-minute video run order
    ├── VendorGate_5min_Talk.pdf  speaker script for the 5-minute talk + cheat sheet
    └── INTERVIEW_QA.md        likely interview questions with answers
```

---

## Configuration

All settings are optional environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `VO_STAGE_DELAY_SECONDS` | `0.6` | Pause between stages so the live view is watchable (set to `0` for instant runs) |
| `VO_REVIEW_RISK_THRESHOLD` | `30` | Cumulative risk score that sends an otherwise clean case to review |
| `VO_BANK_LETTER_MAX_AGE_DAYS` | `90` | Maximum age of a bank confirmation letter |
| `VO_SANCTIONS_REVIEW_SCORE` / `VO_SANCTIONS_BLOCK_SCORE` | `85` / `95` | Watchlist fuzzy-match thresholds |
| `VO_MAX_UPLOAD_MB` | `5` | Per-file upload limit (PDF only, checked by magic bytes) |
| `VO_PUBLIC_BASE_URL` | `http://localhost:8000` | Base for portal links in emails |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `VO_LLM_PROVIDER` | none / `auto` | Optional AI assist |
| `VO_DATA_DIR` | `backend/data` | SQLite DB and uploads |

## Scope and assumptions (short version)

- **India only**: GSTIN, PAN, IFSC, CIN/LLPIN, Udyam. Business types are Private Ltd, Public Ltd, LLP, Partnership and Proprietorship.
- **Mandatory documents**: GST certificate, PAN card, cancelled cheque or bank letter, plus a Certificate of Incorporation for companies. The MSME (Udyam) certificate is required only if the vendor declares MSME.
- Documents are **text PDFs**; scanned images would need OCR, which is on the roadmap.
- All registries, banks, the watchlist and existing vendors are **mocked with fictional data**. Unknown identifiers return a clearly flagged *simulated* response.
- No authentication. Reviewer identity is a typed name, recorded in the audit trail.

The full list, with reasoning, is in [`docs/DESIGN.md`](docs/DESIGN.md).
