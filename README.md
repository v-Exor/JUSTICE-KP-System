# JUSTICE-KP Phase 3

Working thesis prototype for Katarungang Pambarangay hearing transcription, deterministic Phase 2 case analysis, and Phase 3 case decision-support workflow.

Phase 1 remains intact:

- Fully local faster-whisper ASR
- Speech-to-text after recording
- Speaker detection/transcript
- Editable transcript
- Save transcript function

Phase 2 adds:

- Case information intake
- Transcript-based VAWC/sensitive keyword detection
- Rule-based legal entity extraction
- RA 7160 jurisdiction validation
- XAI reasoning trace
- SQLite persistence for saved case analyses

Phase 3 adds:

- Sensitive case routing for VAWC, threats, child abuse, serious injury, outside-KP, and manual review cases
- Referral records with matched keywords and Phase 2 XAI trace references
- Mediation eligibility checking and deterministic mediation suggestions
- Hearing scheduling and timeline tracking
- Evidence upload with optional manual notes
- Lightweight emotion/tension scoring from transcript keywords
- Unified Phase 3 dashboard and human-in-the-loop official decision controls

Phase 4 adds:

- KP form template registry with required fields and usage conditions
- Case-to-form recommendations based on the Phase 3 final action
- Case data auto-fill for generated KP document packets
- Generated packet/form storage with download links
- Missing-field validation, form accuracy percentage, generated-form count, and processing-time metrics
- Phase 4 frontend review panel inside Workflow Outputs

Phase 5 adds:

- Validation dataset management for saved Phase 2/3/4 case outputs
- Ground-truth entry for expected KP coverage, jurisdiction, exclusion ground, referral route, mediation eligibility, form set, keywords, and speaker count
- Automated evaluation against system outputs with accuracy, precision/recall, form accuracy, compliance score, and manual-vs-system processing-time metrics
- Compliance review for consent, anonymization, official decision, generated forms, audit trail, and sensitive-case referral handling
- Experiment run snapshots, CSV export, text report export, and a frontend Validation dashboard for thesis Chapter 4 evidence

JUSTICE-KP is a decision-support system. Final authority remains with barangay officials.

## Tech Stack

- Frontend: Next.js, TypeScript, Tailwind CSS, Axios, Browser MediaRecorder API
- Backend: FastAPI, PostgreSQL in production, SQLite for local development/tests, SQLAlchemy, Alembic, Pydantic
- ASR: local faster-whisper transcription with pyannote speaker diarization
- Phase 2 logic: deterministic Python modules only; no LLM legal decision making

## Run for Local Demo

Double-click **Start JUSTICE-KP Local.cmd** in the project folder to open both
local development server windows. Once they finish starting, open
`http://127.0.0.1:3000`. Leave both windows running; press Ctrl+C in each to stop.
No Tailscale installation or sign-in is required for this launcher.

Use **Start JUSTICE-KP.cmd** for the Tailscale HTTPS configuration. Both launchers
use this same project, data, and ports 3000/8000, so stop both servers before
switching launchers. Local mode does not disable saved Tailscale Serve routes:
disconnect Tailscale on this PC if you want development access limited to this PC.
This launcher is not an isolated copy of the shared application.

Frontend edits usually refresh automatically. Restart the backend after Python
changes. Restart the affected server after environment or dependency changes.

For manual startup, use two separate PowerShell terminals from the project root.

Terminal 1 - backend:

```powershell
.\scripts\run_backend_dev.ps1
```

If port `8000` is already occupied by an old backend run and you want to restart it:

```powershell
.\scripts\run_backend_dev.ps1 -ForceRestart
```

Terminal 2 - frontend:

```powershell
.\scripts\run_frontend_dev.ps1
```

Open the app at:

```text
http://127.0.0.1:3000
```

Default local login:

```text
Username: admin
Password: Admin12345!
```

For a stable login session during demos, always open the frontend with `127.0.0.1`. Do not switch between `localhost` and `127.0.0.1`: browsers treat them as different sites with separate cookies and local storage. The frontend calls the backend using the same hostname at port `8000`.

Backend health check:

```text
http://127.0.0.1:8000
```

During local development, the login page includes a red **Stop Program** button. After confirmation, it stops both the frontend on port `3000` and backend on port `8000`. This control is loopback-only and is disabled when `APP_ENV=production` or `ALLOW_LOCAL_SHUTDOWN` is not `true`.

## Manual Backend Setup

For private access from another device with Tailscale, see
[Tailscale demo setup](docs/Tailscale_Setup.md).
After the initial Tailscale setup, double-click **Start JUSTICE-KP.cmd** in the
project folder to start both servers with the Tailscale settings.

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
cd backend
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Backend URL:

```text
http://127.0.0.1:8000
```

## Manual Frontend Setup

```powershell
cd frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Frontend URL:

```text
http://127.0.0.1:3000
```

## Phase 2 API

`POST /analyze-case`

Accepts either `transcript_id` or `transcript_text` plus case information.

```json
{
  "transcript_text": "Speaker 2: Sinaktan po ako at binantaan ng asawa ko kagabi.",
  "case_information": {
    "case_id": "KP-2026-0001",
    "barangay_name": "Brgy 1 Santa Cruz",
    "city_municipality": "Santa Cruz",
    "case_year": 2026,
    "case_type": "criminal",
    "dispute_category": "physical_injury",
    "complainant_residency": "same_barangay",
    "respondent_residency": "same_barangay",
    "debt_amount_php": 0,
    "maximum_penalty_years": 0,
    "fine_amount_php": 0,
    "government_party_involved": false,
    "already_filed_in_court": false,
    "has_vawc_or_child_abuse_indicators": false
  }
}
```

Returns:

- `extracted_entities`
- `detected_keywords`
- `jurisdiction_decision`
- `exclusion_ground`
- `confidence_level`
- `missing_fields`
- `recommended_next_action`
- `xai_trace`

`POST /save-case-analysis`

Saves one complete `/analyze-case` response to the configured database.

`GET /case-analyses`

Returns saved analysis summaries.

`GET /case-analysis/{id}`

Returns one complete saved analysis.

## Production Database, Migrations, and Backups

Production must run on PostgreSQL. Set `APP_ENV=production` and a PostgreSQL `DATABASE_URL`, for example:

```text
DATABASE_URL=postgresql+psycopg://justicekp:CHANGE_ME@postgres:5432/justicekp
```

SQLite is still supported for local development and unit tests only. When `APP_ENV=production`, backend startup refuses SQLite.

Production schema changes are managed by Alembic:

```powershell
cd backend
alembic upgrade head
```

The production Docker Compose backend runs migrations before starting FastAPI. Backups use:

- SQLite development: encrypted archive containing the SQLite database file.
- PostgreSQL production: encrypted archive containing a `pg_dump` SQL dump plus uploaded evidence/transcripts/generated forms.

Configure retention with:

```text
BACKUP_RETENTION_DAYS=90
BACKUP_RETENTION_COUNT=30
PG_DUMP_PATH=pg_dump
```

Backup retention runs after every backup and can be triggered manually:

- `POST /api/admin/backups/run`
- `POST /api/admin/backups/enforce-retention`
- `POST /api/admin/backups/{backup_id}/verify`

## Transcript Accuracy Reporting

Saved transcripts now persist ASR and diarization quality metrics:

- ASR provider and average confidence
- Diarization quality score
- Expected and detected speaker count
- Manual correction count and manual correction rate

Use:

- `GET /transcripts?q=&page=1&page_size=10` — canonical transcript summaries ordered by ascending transcript number; search is applied before pagination
- `GET /transcripts/{transcript_id}` — full raw and edited transcript content for the selected summary
- `GET /transcripts/accuracy-report`

The paginated list omits large content and segment payloads. These are fetched only for the selected transcript. The metrics support deployment accuracy reporting and help identify recordings that need manual QA or ASR/diarization tuning.

## Sample Test Cases

VAWC/sensitive case transcript:

```text
Speaker 1: Magandang araw po. Ano po ang reklamo ninyo?
Speaker 2: Sinaktan po ako at binantaan ng asawa ko kagabi.
Speaker 3: Hindi po totoo lahat iyon.
```

Expected result:

```json
{
  "detected_keywords": ["sinaktan", "binantaan"],
  "vawc_trigger": true,
  "jurisdiction_decision": "refer_to_pnp_wcpc_or_authority",
  "exclusion_ground": "vawc",
  "recommended_next_action": "Refer to PNP Women and Children Protection Desk. Do not proceed with barangay mediation."
}
```

Normal KP debt case transcript:

```text
Speaker 1: Ano po ang reklamo?
Speaker 2: May utang po siya sa akin na 5000 pesos.
Speaker 3: Totoo po, pero kailangan ko lang po ng hulugan.
```

Expected result when both parties are from the same barangay, no government party is involved, the case is not filed in court, penalty is `<= 1` year, and fine is `<= 5000`:

```json
{
  "dispute_category": "debt",
  "vawc_trigger": false,
  "jurisdiction_decision": "within_kp",
  "exclusion_ground": "none"
}
```

## Phase 2 Modules

- `backend/keyword_detector.py`: sensitive keyword scan
- `backend/legal_ner.py`: simple rule-based legal entity extraction
- `backend/rule_engine.py`: deterministic RA 7160 jurisdiction rules
- `backend/xai_trace.py`: readable fired/not-fired rule trace
- `backend/schemas.py`: Pydantic API contracts

The KP fine threshold used by rule `KP-COVER-05` is PHP 5,000.

## Phase 3 API

Phase 3 uses saved Phase 2 `CaseAnalysis` records as the case anchor. Save a Phase 2 analysis first, then run:

`POST /api/phase3/process-case/{case_id}`

This creates or updates routing, eligibility, mediation suggestions, emotion analysis, and any automatic referral record.

Key endpoints:

- `GET /api/phase3/dashboard/{case_id}`
- `POST /api/phase3/sensitive-routing/{case_id}`
- `POST /api/phase3/mediation-eligibility/{case_id}`
- `POST /api/phase3/mediation-suggestions/{case_id}`
- `POST /api/phase3/hearings`
- `POST /api/phase3/evidence/upload/{case_id}`
- `POST /api/phase3/emotion-analysis/{case_id}`
- `POST /api/phase3/official-decision/{case_id}`

The frontend exposes these through **Workflow Panel 8: Outputs** as the **Case Decision Summary**.

## Phase 4 API

Phase 4 turns saved Phase 3 decisions into generated KP form packets:

- `GET /api/phase4/form-templates`
- `GET /api/phase4/recommendations/{case_id}`
- `POST /api/phase4/generate-packet/{case_id}`
- `GET /api/phase4/packets/{case_id}`
- `GET /api/phase4/generated-forms/{generated_form_id}/download`

Generated PDFs are stored in `backend/generated_forms`. The original official templates remain available through `/api/kp-forms`.

## Completed transcript PDF

The completed-case screen exports the latest final reviewer-approved transcript through:

- `GET /api/management/cases/{workflow_id}/transcript.pdf`

The server enforces case ownership, sensitive-case access, `transcript.read`, and `reports.export`. It returns an A4 Unicode PDF with the final outcome, finalization and generation metadata, speaker labels, available timestamps, page numbers, confidentiality notice, and decision-support disclaimer. Each successful generation/download creates an audit event containing the document ID, SHA-256 hash, byte length, page count, transcript ID, user, and generation time. The hash is also returned in `X-Document-SHA256`.

Finalized workflows and their linked transcripts are immutable through ordinary update/delete endpoints. A future retention implementation must use a separate explicitly authorized retention action.

## Phase 5 API

Phase 5 turns saved operational cases into a validation dataset for thesis evaluation:

- `GET /api/phase5/dataset`
- `POST /api/phase5/import-case/{case_id}`
- `PATCH /api/phase5/ground-truth/{case_id}`
- `PATCH /api/phase5/compliance/{case_id}`
- `POST /api/phase5/evaluate/{case_id}`
- `POST /api/phase5/evaluate-all`
- `GET /api/phase5/metrics`
- `POST /api/phase5/experiment-runs`
- `GET /api/phase5/experiment-runs`
- `GET /api/phase5/export/csv`
- `GET /api/phase5/export/report`
- `GET /api/phase5/export/report.pdf`

The frontend exposes this as the **Validation** tab. Import saved case analyses, add ground-truth labels, save compliance checks, run evaluation, and export thesis-ready metrics.

## Phase 3 Database Notes

The Concept Paper Table 2 research schema is preserved in `kp_research_dataset` with these columns:

```text
audio_id, barangay_name, city_municipality, case_year, case_type,
dispute_category, complainant_residency, respondent_residency,
debt_amount_php, penalty_years_max, vawc_trigger, speaker_count,
emotion_tension, covered_under_kp, kp_exclusion_ground,
jurisdiction_decision, processing_time_min, form_accuracy_pct,
xai_trace_length
```

Operational Phase 3, Phase 4, and Phase 5 data is stored separately in `phase3_case_routes`, `referrals`, `mediation_eligibility`, `mediation_suggestions`, `hearings`, `evidence`, `emotion_analysis`, `audit_logs`, `phase3_official_decisions`, `phase4_form_packets`, `phase4_generated_forms`, `phase5_validation_cases`, `phase5_ground_truth`, `phase5_evaluation_results`, `phase5_compliance_reviews`, and `phase5_experiment_runs`.

## Tests

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover backend
```

Run frontend type checks:

```powershell
cd frontend
npx tsc --noEmit
```

## Out of Scope

This prototype does not add complex ML legal NER, CNN emotion training, physical template field stamping, or a full PostgreSQL/Alembic migration.
