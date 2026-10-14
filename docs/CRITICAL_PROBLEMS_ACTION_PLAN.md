# JUSTICE-KP Critical Problems Action Plan

**Purpose:** Central working document for resolving the six critical problems identified in the system audit before the Final Oral Defense.

**Current assessment:** The functional prototype is substantially implemented, but it is not yet defense-ready as an experimental research system. The largest gaps are the unfinished Phase 5 evaluation, inconsistent local data, broken production packaging, unvalidated sensitive-case classification, incomplete security controls, and an outdated manuscript.

> JUSTICE-KP must be presented as a human-in-the-loop decision-support prototype. It must not be described as an autonomous legal adjudicator or as having achieved performance targets that have not been measured.

## How to Use This Document

- Work through the problems in the priority order shown below.
- Do not clean or replace the current database until a backup has been created and verified.
- Keep measurements reproducible: record the dataset version, code version, configuration, evaluator, and execution date for every final experiment run.
- Mark a problem complete only after all acceptance criteria and verification steps pass.
- Preserve failed/error cases. They are required for defensible Chapter 4 error analysis.

## Priority Summary

| Priority | Critical problem | Current condition | Target condition |
|---|---|---|---|
| P0 | 1. Phase 5 experiment incomplete | 1 validation case and 0 evaluation results | Reviewed dataset evaluated with reproducible metrics and error analysis |
| P0 | 2. Database integrity problems | Hundreds of orphaned Phase 3/4 records | Clean, backed-up, internally consistent research database |
| P0 | 3. Production deployment broken | Docker build/configuration cannot be relied upon | Reproducible frontend/backend/PostgreSQL deployment |
| P0 | 4. Sensitive-case classification risk | Generic words can be labeled as VAWC | Separated, reviewed, and measured safety classifications |
| P1 | 5. Security/privacy gaps | Several documented controls are incomplete | Enforced sensitive access, secure admin setup, auditability, and retention |
| P0 | 6. Manuscript-system mismatch | Manuscript contains obsolete claims and no final Phase 4/5 results | Manuscript accurately reflects implementation and measured results |

---

## 1. Phase 5 Experiment Has Not Been Completed

### Audit Evidence

The active Phase 5 data contained:

- **1** validation case
- **1** ground-truth record
- **1** compliance review
- **0** evaluation results
- **1** experiment-run record
- No computed overall accuracy
- No jurisdiction accuracy
- No sensitive-case accuracy
- No referral accuracy
- No mediation accuracy
- No form recommendation accuracy
- No keyword precision or recall
- No compliance average
- No manual-versus-system processing-time result

The source workbook contains **539 cases**:

- **114** cases derived from real PDFs
- **425** synthetic cases
- 49 cases in each of 11 case-type groups
- Labels represented in the workbook:
  - 245 `KP_COVERED_AMICABLE`
  - 49 `REFER_VAWC_CHILD_PROTECTION`
  - 49 `NON_KP_REVIEW`
  - 196 `NON_KP_REFERRAL`

### Why This Is Critical

The evaluation subsystem exists, but the experiment itself has not produced results. Consequently, claims such as **90% processing-time improvement**, **95% accuracy**, or **100% VAWC recall** cannot currently be defended as achieved results. They must remain targets or hypotheses until supported by reviewed Phase 5 outputs.

### Required Work

- [ ] Freeze the dataset version used for the final experiment.
- [ ] Assign a version/name to the final experimental dataset.
- [ ] Document the inclusion and exclusion criteria for the 539 cases.
- [ ] Explain how the 114 real-PDF-derived cases were anonymized and prepared.
- [ ] Explain how the 425 synthetic cases were generated and how synthetic-data bias is controlled.
- [ ] Rebuild or populate the Phase 5 validation dataset from a clean, consistent database.
- [ ] Verify that every imported validation case has a corresponding Phase 2 analysis.
- [ ] Verify that every imported validation case has the expected Phase 3 routing outputs.
- [ ] Review ground-truth jurisdiction decisions with a qualified reviewer.
- [ ] Review exclusion grounds, especially penalty, government-party, already-filed, and different-jurisdiction cases.
- [ ] Review all 49 VAWC/child-protection ground-truth cases manually.
- [ ] Separate VAWC, child abuse, threats, serious injury, and generic safety indicators in the ground truth.
- [ ] Add expected keywords where keyword precision and recall will be reported.
- [ ] Add expected form IDs where form recommendation accuracy will be reported.
- [ ] Confirm expected speaker count only for records where speaker-count evaluation is meaningful.
- [ ] Record manual processing time using a documented timing protocol.
- [ ] Record system processing time using the same start and end boundaries.
- [ ] Complete the compliance review for each case or for the documented evaluation sample.
- [ ] Run Phase 5 evaluation for every eligible case.
- [ ] Create a named final experiment run after evaluation.
- [ ] Export full and anonymized CSV reports.
- [ ] Export full and anonymized PDF/text reports.
- [ ] Preserve and categorize every mismatch for Chapter 4 error analysis.
- [ ] Report results separately for real-derived and synthetic cases where possible.
- [ ] Report results per case category, not only as a single overall percentage.

### Metrics Required for Chapter 4

- Overall accuracy
- Jurisdiction accuracy
- Sensitive-case accuracy
- Referral-route accuracy
- Mediation-eligibility accuracy
- Form recommendation accuracy
- Keyword precision
- Keyword recall
- Speaker-count accuracy, if the data supports it
- Average Phase 4 required-field/form accuracy
- Compliance score
- Average manual processing time
- Average system processing time
- Average minutes saved
- Average percentage of time saved
- Error counts and representative error cases

### Acceptance Criteria

- [ ] The final number of imported cases is documented and reconciled with the 539-row workbook.
- [ ] Every evaluated record has reviewed ground truth.
- [ ] No final metric is `None` unless the manuscript explicitly explains why it is not applicable.
- [ ] Every reported number can be reproduced from a saved experiment run or exported report.
- [ ] Real-derived and synthetic case counts are visible in the methodology and results.
- [ ] Error cases are reviewed and discussed rather than removed to improve the metrics.
- [ ] Chapter 4 uses measured values only.

### Verification

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_phase5_services -v
```

In the application:

1. Open **Validation**.
2. Confirm the expected dataset count.
3. Confirm ground truth and compliance reviews are populated.
4. Run **Evaluate All**.
5. Confirm all required aggregate metrics are populated.
6. Create a final named experiment run.
7. Export and archive the anonymized CSV and PDF report.

---

## 2. Database Integrity Problems

### Audit Evidence

The audited local SQLite database contained:

- 24 `case_information` rows representing only **6 distinct case IDs**
- **544 distinct** Phase 3 route case IDs
- **539** Phase 3 route records without matching case information
- **539** mediation-eligibility records without matching case information
- **544 distinct** Phase 4 packet case IDs
- **674** Phase 4 packet records without matching case information
- **1,173** generated-form database records/files
- 540 distinct research-dataset audio IDs versus 539 workbook cases
- 0 generated-form records without a Phase 4 packet, meaning the form-to-packet relationship existed even while many packet-to-case relationships were stale

### Why This Is Critical

The database mixes operational cases, generated validation artifacts, and stale/orphaned records. Metrics produced from this state may be misleading. Deleting a source case also appears capable of leaving Phase 3, Phase 4, uploaded, or generated artifacts behind. This creates reproducibility, privacy, storage, and research-validity problems.

### Safety Rule Before Repair

> Do not delete, rebuild, migrate, or overwrite the current database until an encrypted backup has been created, downloaded, and successfully verified.

### Required Work

- [ ] Stop using the current database for final experiment measurements.
- [ ] Create and verify an encrypted backup.
- [ ] Copy the database and runtime artifact directories to a dated archive.
- [ ] Produce a reconciliation report before deleting anything.
- [ ] Identify the source of the 539 orphaned Phase 3 records.
- [ ] Identify the source of the 674 orphaned Phase 4 packet records.
- [ ] Reconcile the 540 research rows with the 539 workbook cases.
- [ ] Determine whether the extra research row is an operational/manual case or an accidental duplicate.
- [ ] Identify repeated Phase 4 packet generation and decide which packet is canonical.
- [ ] Check whether all 1,173 generated PDF paths exist.
- [ ] Check for generated PDFs that have no database record.
- [ ] Check uploaded audio, transcripts, evidence, and consent files for missing database references.
- [ ] Create a clean database dedicated to the final experiment.
- [ ] Import the workbook through one documented, idempotent process.
- [ ] Verify counts after import before generating Phase 3/4/5 artifacts.
- [ ] Add or enforce relationships/cascade behavior where deletion should remove dependent records.
- [ ] Where deletion must not cascade for legal/audit reasons, implement explicit archival and retention behavior.
- [ ] Enable and test SQLite foreign-key enforcement in development/tests if SQLite remains supported.
- [ ] Add an integrity-check command or administrative report.
- [ ] Add tests for source-case deletion, artifact cleanup/archival, and orphan prevention.
- [ ] Keep operational/demo data separate from the final research database.

### Recommended Clean Experimental Flow

1. Create a verified backup of the current state.
2. Create a new empty database.
3. Run schema creation/migrations.
4. Import all selected workbook cases once.
5. Verify Phase 2 record counts and unique case IDs.
6. Generate Phase 3 outputs once per case.
7. Generate one canonical Phase 4 packet per required case/action.
8. Populate Phase 5 validation and reviewed ground truth.
9. Run evaluation.
10. Save a final experiment snapshot and exports.

### Acceptance Criteria

- [ ] Every Phase 3 route resolves to an existing canonical case.
- [ ] Every mediation, referral, hearing, evidence, and emotion record resolves to an existing case.
- [ ] Every Phase 4 packet resolves to an existing case.
- [ ] Every generated form resolves to an existing packet and existing file.
- [ ] Every Phase 5 validation case resolves to an existing Phase 2 analysis.
- [ ] Workbook rows, research rows, validation cases, and documented exclusions reconcile exactly.
- [ ] Re-running the importer with `skip_existing` does not create duplicates.
- [ ] The final experiment database is archived and reproducible.

### Verification

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_kp_cases_importer -v
.\.venv\Scripts\python.exe -m unittest backend.test_workflow_e2e -v
```

Also run a database integrity report that checks missing parent records, duplicate canonical case IDs, missing files, and unreferenced files.

---

## 3. Production Deployment Is Broken as Written

### Audit Evidence

#### Frontend Docker build blocker

`frontend/Dockerfile` runs:

```dockerfile
RUN npm run build
```

However, `frontend/package.json` currently defines only `dev` and `start`. The exact command fails with:

```text
npm error Missing script: "build"
```

A direct `npx next build` succeeds, proving that the source compiles but the packaged production workflow is incomplete.

#### Incorrect PostgreSQL host for Docker

`.env.production.example` uses:

```text
DATABASE_URL=postgresql+psycopg://justicekp:CHANGE_ME@127.0.0.1:5432/justicekp
```

Inside the backend container, `127.0.0.1` refers to the backend container itself, not the Compose `postgres` service. The container configuration should use the service hostname, normally `postgres`.

#### Storage-volume mismatch

Compose mounts:

```text
/app/backend/data
/app/backend/backups
```

The main application currently writes operational files to hardcoded directories such as:

```text
/app/backend/uploads
/app/backend/transcripts
/app/backend/evidence_uploads
/app/backend/generated_forms
/app/backend/consent_uploads
```

The backup service reads environment-configurable paths, but `main.py` does not use the same environment variables. This can cause backups to read from different directories than the application writes to, and application files may disappear when containers are replaced.

#### Frontend API configuration concern

Compose sets `NEXT_PUBLIC_API_BASE_URL` at container runtime. Next.js public environment values are normally compiled into the browser bundle at build time. The current frontend fallback to the browser hostname may work on a LAN, but the production behavior must be made explicit and tested instead of relying on an ineffective runtime variable.

#### Environment/tooling state

- `.env.production` does not exist.
- Docker was not installed on the audited development machine.
- The `.git` directory exists but is empty, so Git does not recognize the workspace as a repository.
- There is no usable version history or rollback point in this workspace.

### Required Work

- [ ] Add a `build` script to `frontend/package.json`.
- [ ] Add explicit `lint`, `typecheck`, and `test` scripts as appropriate.
- [ ] Ensure the Dockerfile uses a valid production build command.
- [ ] Change the container PostgreSQL hostname from `127.0.0.1` to `postgres`.
- [ ] Use strong non-example PostgreSQL credentials.
- [ ] Make the application and backup service use the same environment-configurable storage paths.
- [ ] Add `CONSENT_DIR` to the production configuration and persistent storage plan.
- [ ] Mount every required persistent directory or use one consistently configured data root.
- [ ] Ensure generated forms, consent, evidence, transcripts, uploads, and backups survive container replacement.
- [ ] Decide whether the frontend API URL is build-time configuration or runtime configuration.
- [ ] Pass `NEXT_PUBLIC_API_BASE_URL` at build time if keeping the current Next.js public variable.
- [ ] Create a real `.env.production` outside version control.
- [ ] Reject placeholder values such as `CHANGE_ME` during production startup.
- [ ] Install Docker/Compose on the intended deployment machine or document an alternative deployment process.
- [ ] Run PostgreSQL migrations on a clean database.
- [ ] Add a PostgreSQL integration/smoke test.
- [ ] Test backup creation and verification against PostgreSQL using `pg_dump`.
- [ ] Test container restart and confirm files/data remain available.
- [ ] Restore or initialize a valid Git repository before major repairs.
- [ ] Commit a known-good baseline before database/security changes.

### Suggested Frontend Scripts

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "typecheck": "tsc --noEmit"
  }
}
```

Add lint/test scripts only after confirming compatibility with the installed Next.js and ESLint versions.

### Acceptance Criteria

- [ ] `npm run build` passes.
- [ ] The frontend Docker image builds without modifying files interactively.
- [ ] The backend Docker image builds.
- [ ] Compose starts PostgreSQL, backend, and frontend successfully.
- [ ] The backend connects to the Compose PostgreSQL service.
- [ ] Alembic reaches the expected head revision.
- [ ] Frontend login reaches the correct backend from another LAN device.
- [ ] A created case survives a full container restart/recreation.
- [ ] Uploaded audio, consent, evidence, transcripts, generated forms, and backups survive recreation.
- [ ] A PostgreSQL backup can be created and verified.
- [ ] Production secrets are not committed.
- [ ] The project has valid version control and a rollback baseline.

### Verification

```powershell
cd frontend
npm.cmd run build
npx.cmd tsc --noEmit

cd ..
docker compose -f docker-compose.production.yml config
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d
```

After startup, verify frontend, backend health, login, case creation, file persistence, migrations, and backups.

---

## 4. Sensitive-Case Classification Can Produce False VAWC Referrals

### Audit Evidence

Phase 2 uses a shared sensitive-keyword list. Any match sets:

```text
vawc_trigger = true
```

The list contains specific violence terms but also generic/context-dependent terms including:

- `hurt`
- `injured`
- `bata`
- general violence or injury wording

Phase 2 then maps this trigger to:

- `refer_to_pnp_wcpc_or_authority`
- exclusion ground `vawc`
- a PNP Women and Children Protection Desk referral recommendation

Phase 3 has separate category logic, but its VAWC keyword list also contains standalone terms such as:

- `asawa`
- `bata`
- general injury terms

Standalone occurrence does not establish the legal relationship, victim class, context, severity, or offense required to accurately classify a case as VAWC or child abuse.

### Why This Is Critical

Conservative safety routing is appropriate, but the current names and outputs can overstate what the keyword detector has established. False positives may reduce precision and may incorrectly present generic threats/injuries as confirmed VAWC. False negatives remain possible for implied facts, slang, misspellings, unusual wording, or facts absent from the transcript.

### Required Design Change

Separate **detection** from **legal/official classification**.

Recommended signal categories:

1. `vawc_indicator`
2. `child_protection_indicator`
3. `threat_indicator`
4. `serious_injury_indicator`
5. `generic_violence_indicator`
6. `manual_safety_review_indicator`

The system may block automatic mediation when a safety indicator exists, but it should not label every safety signal as confirmed VAWC.

### Required Work

- [ ] Rename or redesign the generic `vawc_trigger` field.
- [ ] Preserve compatibility for existing records or provide a data migration.
- [ ] Split the sensitive keyword list into reviewed category-specific lists.
- [ ] Remove standalone relationship words such as `asawa` as sufficient VAWC evidence.
- [ ] Remove standalone age words such as `bata` as sufficient child-abuse evidence.
- [ ] Treat generic injury words as safety/manual-review signals unless supporting context is present.
- [ ] Add context rules for intimate/family relationship indicators.
- [ ] Add context rules for child/minor victim indicators.
- [ ] Add negation handling where practical, such as “hindi niya ako sinaktan.”
- [ ] Add tests for quotations, denials, hypothetical wording, and third-party descriptions.
- [ ] Add spelling/Taglish variants only when supported by reviewed data.
- [ ] Ensure Phase 2 and Phase 3 use one canonical classification taxonomy.
- [ ] Make the frontend display “safety indicator detected” until an official classification is confirmed.
- [ ] Preserve the mediation safety block when warranted.
- [ ] Allow an authorized official to confirm or override the category with a required reason.
- [ ] Record the system signal and official category separately in the audit trail.
- [ ] Review the taxonomy and referral destinations with the thesis adviser and a qualified legal/domain reviewer.
- [ ] Re-run all 49 VAWC/child-protection cases after the change.
- [ ] Include negative controls containing `asawa`, `bata`, `hurt`, and `injured` in non-VAWC contexts.

### Minimum Test Scenarios

- Confirmed intimate-partner physical violence
- Confirmed intimate-partner threat
- Child abuse with explicit abuse context
- Minor mentioned without abuse
- Spouse mentioned in an ordinary debt/property disagreement
- Minor physical injury within potentially eligible KP limits
- Serious physical injury
- Generic threat without intimate-partner context
- Negated allegation
- Historical or third-party quotation
- Ambiguous wording requiring manual review
- Misspelled or Taglish safety wording

### Required Experimental Reporting

- Confusion matrix for sensitive classification
- Precision and recall per sensitive category
- False-positive count and examples
- False-negative count and examples
- Separate results for real-derived and synthetic cases
- Explanation that final classification/referral remains a human decision

### Acceptance Criteria

- [ ] A generic safety word does not automatically become confirmed VAWC.
- [ ] An ordinary spouse-related dispute without violence does not automatically route to WCPD.
- [ ] A child/minor mention without abuse does not automatically become child abuse.
- [ ] Confirmed high-risk cases still block automatic mediation.
- [ ] Each category has reviewed positive and negative tests.
- [ ] Phase 2, Phase 3, Phase 5, frontend labels, and manuscript terminology agree.
- [ ] Final precision/recall is measured on reviewed ground truth.

### Verification

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_rule_engine_ra7160 -v
.\.venv\Scripts\python.exe -m unittest backend.test_phase3_services -v
.\.venv\Scripts\python.exe -m unittest backend.test_workflow_e2e -v
```

Add dedicated sensitive-classification tests before considering this problem complete.

---

## 5. Security and Privacy Controls Are Incomplete

### Audit Evidence

The system already includes useful controls:

- Password hashing with PBKDF2
- HttpOnly session cookies
- CSRF protection for mutating requests
- Role/permission definitions
- Restricted production CORS configuration
- Security response headers
- Authentication and several workflow audit events
- Encrypted backup creation and verification
- Anonymized Phase 5 exports

However, the following gaps remain.

### 5.1 Default Administrator Risk

The backend automatically seeds an administrator when the database has no users. If `DEV_ADMIN_PASSWORD` is not supplied, it uses:

```text
Admin12345!
```

The seeded administrator has `must_change_password=False`. Production configuration does not require `DEV_ADMIN_PASSWORD`, and startup does not reject the known default.

#### Required Work

- [ ] Never automatically seed the known development password in production.
- [ ] Require an explicit strong initial-admin secret or separate one-time provisioning command.
- [ ] Reject known/default passwords during production startup.
- [ ] Set `must_change_password=True` for newly provisioned administrators.
- [ ] Add an enforced password-change workflow.
- [ ] Add tests for production startup without a secure admin setup.

### 5.2 No Login Rate Limiting or Lockout

Login attempts are recorded, but repeated failed logins are not delayed, blocked, or rate-limited.

#### Required Work

- [ ] Define an account/IP throttling policy.
- [ ] Add a bounded failed-attempt window and temporary lockout/backoff.
- [ ] Avoid revealing whether a username exists.
- [ ] Audit lockout and recovery events.
- [ ] Add tests for repeated failures and successful recovery.

### 5.3 Sensitive Records Are Not Enforced Separately

The role matrix states that sensitive cases require elevated permissions, but API access is based mostly on broad permissions such as `case.read` and `transcript.read`. The application does not consistently filter by `sensitivity_level` before returning case details, transcripts, Phase 3 dashboards, forms, or reports.

#### Required Work

- [ ] Define a `sensitive_case.read` permission.
- [ ] Define whether researchers may access only anonymized sensitive records.
- [ ] Enforce sensitivity checks inside service/endpoint queries, not only in frontend navigation.
- [ ] Prevent viewers from retrieving sensitive case details.
- [ ] Prevent researchers from retrieving identifiable sensitive transcripts unless explicitly authorized.
- [ ] Add object-level authorization tests for each role.
- [ ] Ensure case lists do not reveal sensitive identifiers to unauthorized roles.

### 5.4 Downloads and Exports Are Not Fully Audited

The security review says exports and evidence downloads are audited. The audited endpoints for the following actions do not create matching audit events:

- Official KP template downloads
- Generated Phase 4 form downloads
- Evidence downloads
- Full Phase 5 CSV export
- Anonymized Phase 5 CSV export
- Text report export
- Full PDF report export
- Anonymized PDF report export
- Audio streaming/download access

#### Required Work

- [ ] Add actor-aware audit logging to each download/export endpoint.
- [ ] Record resource type, resource ID, case ID where applicable, actor, role, IP, user agent, timestamp, anonymized/full export type, and risk level.
- [ ] Avoid putting sensitive file paths or content in audit details.
- [ ] Add audit assertions to endpoint tests.

### 5.5 Consent Uploads Are Not Properly Managed

Consent files are written to disk and their metadata is returned to the frontend, but there is no dedicated consent-file database model or retrieval/download endpoint. The workflow draft stores frontend metadata, not a durable authorized file relationship. Deleting or abandoning a draft can leave files behind.

#### Required Work

- [ ] Create a consent-file database record linked to the workflow/case and party type.
- [ ] Store a server-side path, checksum, MIME type, size, uploader, and timestamps.
- [ ] Add an authorized download/view endpoint.
- [ ] Add replacement, archival, and deletion/retention behavior.
- [ ] Audit upload, view/download, replacement, and deletion.
- [ ] Include consent files in backup/restore verification.
- [ ] Add missing-file and orphan-file checks.

### 5.6 Upload Size Is Checked After the Full File Is Written

Audio, evidence, and consent uploads are copied completely before the maximum-size check runs. An oversized request can consume disk space before being rejected.

#### Required Work

- [ ] Reject requests using a trusted `Content-Length` when available and excessive.
- [ ] Stream uploads in bounded chunks.
- [ ] Stop writing and delete the partial file immediately when the byte limit is exceeded.
- [ ] Apply the same implementation to audio, evidence, and consent files.
- [ ] Add tests for files just below, equal to, and above the limit.
- [ ] Consider MIME/content validation rather than trusting only the extension.

### 5.7 Retention Policy Is Not Enforced

The privacy policy provides only general guidance, while backup documentation and environment defaults use different retention descriptions. There is no demonstrated scheduler enforcing operational record retention for transcripts, audio, evidence, consent, and generated forms.

#### Required Work

- [ ] Define one approved retention schedule.
- [ ] Resolve the mismatch between 90-day/count environment defaults and the daily/weekly policy text.
- [ ] Separate backup retention from operational-record retention.
- [ ] Implement a reviewed archival/deletion process.
- [ ] Respect legal holds and sensitive-case requirements.
- [ ] Audit every archival/deletion event.
- [ ] Add a dry-run retention report before enabling deletion.

### 5.8 Security Review Is Not Signed Off

`docs/security/Security_Review_Report.md` has blank reviewer, date, findings, and required-fixes fields.

#### Required Work

- [ ] Update the report with the actual findings in this section.
- [ ] Assign a reviewer who is not the sole implementer where possible.
- [ ] Record residual risks and deployment restrictions.
- [ ] Obtain sign-off before any live barangay deployment.

### Acceptance Criteria

- [ ] Production cannot start with a known default administrator password.
- [ ] Newly provisioned administrators must change their password.
- [ ] Repeated login failures are rate-limited or temporarily locked.
- [ ] Sensitive data access is enforced by role and object sensitivity.
- [ ] Every download/export listed above creates an audit event.
- [ ] Consent files are durable, retrievable only by authorized users, backed up, and auditable.
- [ ] Oversized uploads stop during streaming rather than after full disk write.
- [ ] Retention rules are documented consistently and have a dry-run report.
- [ ] Security tests pass and the review has a completed sign-off.

### Verification

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_production_hardening -v
.\.venv\Scripts\python.exe -m unittest discover backend -v
```

Add API-level RBAC, rate-limit, audit-download, consent-file, and oversized-upload tests.

---

## 6. Manuscript Does Not Match the Implemented System

### Audit Evidence

The current manuscript artifacts do not describe the present implementation:

- `Chapter_1-3.pdf` contains references to Experta, CalamanCy, CNN components, and unproven 90%/95% performance figures.
- It contains no Phase 4 or Phase 5 discussion.
- `THESIS-MANUSCRIPT.pdf` also contains no Phase 4 or Phase 5 discussion.
- The concept paper contains multiple Experta, CalamanCy, CNN, 90%, and 95% references.
- The manuscript update plan explicitly warns against claiming unimplemented components.
- The root README is still titled **JUSTICE-KP Phase 3**, although Phases 4 and 5 are implemented.
- The README says a full PostgreSQL/Alembic migration is out of scope even though a production configuration and initial migration exist.
- The application metadata says JUSTICE-KP 2.0, while the backend API version is 6.0.0 and the README says Phase 3.

### Claims That Must Be Removed or Corrected

Do not claim that the implemented prototype currently uses:

- Experta forward chaining
- CalamanCy NER
- GPT-4o-mini mediation generation
- CNN emotion recognition
- Whisper LoRA trained for a Laguna dialect
- OCR evidence extraction
- Complete offline PWA functionality
- Complete physical field stamping of official KP templates
- Autonomous legal decision-making

Use the implemented descriptions instead:

- Deterministic Python RA 7160/KP rule engine
- Regex and rule-based legal entity extraction
- Deterministic mediation suggestion templates
- Keyword-based emotion/tension signals
- Fully local faster-whisper ASR
- Optional pyannote diarization with fallback speaker assignment
- Browser MediaRecorder recording
- Phase 4 PDF review packets/data attachments requiring official review
- Human-in-the-loop decision support

### Performance-Claim Rule

Claims such as the following must remain targets/hypotheses until Phase 5 proves them:

- 90% processing-time improvement
- 95% accuracy
- 100% VAWC recall
- Any other precision, recall, compliance, form-accuracy, or time-saving percentage

### Required Work by Chapter

#### Chapter 1

- [ ] Update the system description to match the implemented prototype.
- [ ] Complete the specific objectives.
- [ ] Complete Scope and Limitations.
- [ ] State that barangay officials retain final authority.
- [ ] Remove or qualify unsupported national/performance claims.
- [ ] Include limits of ASR, deterministic keywords/rules, diarization, form generation, and ground-truth dependence.

#### Chapter 2

- [ ] Reorganize the literature review around speech-to-text, barangay systems, rule-based legal decision support, XAI, sensitive routing, form automation, and software validation.
- [ ] Remove synthesis that depends on unimplemented AI components.
- [ ] Ensure every technical/legal claim has a valid source.

#### Chapter 3

- [ ] Describe developmental plus experimental/evaluation research design.
- [ ] Document the final study locale and evaluator roles.
- [ ] Describe the 539-case dataset and real/synthetic split.
- [ ] Document ground-truth review procedures.
- [ ] Document transcription, normalization, keyword detection, RA 7160 rules, routing, form generation, and Phase 5 evaluation algorithms.
- [ ] Include the actual architecture and database entities.
- [ ] Include privacy, consent, anonymization, and retention procedures.
- [ ] Include functional, integration, security, and user-acceptance testing methods.
- [ ] Explain all evaluation formulas.

#### Chapter 4

- [ ] Write only after final Phase 5 evaluation.
- [ ] Include functional test results per phase.
- [ ] Include jurisdiction and sensitive-category confusion matrices.
- [ ] Include referral and mediation accuracy.
- [ ] Include keyword precision/recall.
- [ ] Include form accuracy.
- [ ] Include compliance results.
- [ ] Include manual-versus-system processing time.
- [ ] Separate real-derived and synthetic results where possible.
- [ ] Include representative false positives, false negatives, and mitigations.

#### Chapter 5

- [ ] Write only after Chapter 4 is final.
- [ ] Base conclusions strictly on measured results.
- [ ] State limitations without hiding poor/error cases.
- [ ] Recommend future ASR adaptation, larger field evaluation, richer NLP only when supported, and stronger form stamping/privacy controls.

### Figures and Appendices Required

- [ ] Final system architecture
- [ ] End-to-end workflow diagram
- [ ] RA 7160 rule flow
- [ ] Sensitive routing flow
- [ ] Phase 4 form flow
- [ ] Phase 5 validation flow
- [ ] Database/data dictionary
- [ ] Functional test report
- [ ] Evaluation instrument and ground-truth protocol
- [ ] Anonymized sample output
- [ ] User manual
- [ ] Deployment and backup procedure
- [ ] Security/privacy checklist
- [ ] Screenshots of the final tested system

### Documentation Consistency Work

- [ ] Rename/update the README title.
- [ ] Correct the outdated “Out of Scope” statement.
- [ ] Choose one consistent product/release naming scheme.
- [ ] Synchronize README, frontend metadata, backend version, diagrams, screenshots, and manuscript terminology.
- [ ] Ensure all screenshots show the final interface and final labels.

### Acceptance Criteria

- [ ] The manuscript contains no claim that contradicts the source code.
- [ ] Every achieved percentage is traceable to the final Phase 5 experiment.
- [ ] Phases 1 through 5 are described accurately.
- [ ] Real-derived and synthetic data are disclosed clearly.
- [ ] Sensitive classification is described as decision support with human confirmation.
- [ ] Scope and limitations are complete.
- [ ] Chapter 4 contains reproducible metrics and error analysis.
- [ ] Chapter 5 conclusions follow directly from Chapter 4.
- [ ] README, application names/versions, diagrams, and manuscript are consistent.
- [ ] The adviser-approved final manuscript is archived with the final code/dataset version.

---

## Final Cross-System Verification Checklist

Run this checklist only after the six problems have been addressed.

### Automated Checks

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover backend -v

cd frontend
npx.cmd tsc --noEmit
npm.cmd run build
```

Expected minimum result:

- [ ] Python compilation passes.
- [ ] Python dependency check passes.
- [ ] All backend tests pass.
- [ ] TypeScript passes.
- [ ] The exact production frontend command passes.
- [ ] No critical lint/build warnings remain.

### Manual End-to-End Scenarios

- [ ] Normal within-KP debt case
- [ ] Confirmed VAWC case
- [ ] Child-protection case
- [ ] Threat case without VAWC context
- [ ] Serious-injury case
- [ ] Government-party case
- [ ] Already-filed-in-court case
- [ ] Penalty-over-one-year case
- [ ] Fine-over-PHP-5,000 case
- [ ] Ambiguous/manual-review case
- [ ] Negated or context-dependent safety wording
- [ ] Consent upload and authorized retrieval
- [ ] Evidence upload and authorized retrieval
- [ ] Official decision and audit trail
- [ ] Form generation, review, and authorized download
- [ ] Phase 5 evaluation and anonymized export
- [ ] Backup creation, verification, restart, and documented restore rehearsal

### Defense Readiness Gate

The system is ready for the Final Oral Defense only when:

- [ ] The final experiment has reviewed, reproducible metrics.
- [ ] Database counts reconcile and no unexplained orphan records remain.
- [ ] The production build/deployment process works.
- [ ] Sensitive-case behavior has reviewed positive and negative evidence.
- [ ] Security findings are fixed or explicitly documented as prototype limitations.
- [ ] The manuscript matches the implemented and measured system.
- [ ] A complete demo rehearsal succeeds using the final code and final database.

## Current Verified Strengths to Preserve

The remediation work should preserve the following verified behavior:

- All 47 existing backend tests passed during the audit.
- Python compilation passed.
- Installed Python requirements passed dependency checking.
- TypeScript checking passed.
- Direct Next.js production compilation passed.
- The local frontend and backend returned HTTP 200.
- The backend exposed 74 API paths.
- Protected APIs rejected unauthenticated access.
- CORS rejected an unapproved origin.
- Security response headers were present.
- FFmpeg worked.
- Local faster-whisper transcription completed without an online ASR dependency.
- faster-whisper, PyTorch, torchaudio, and pyannote imported successfully.
- Normal KP, VAWC referral, outside-KP referral, and manual-review end-to-end backend flows passed.

Do not weaken these verified behaviors while fixing the critical problems.
