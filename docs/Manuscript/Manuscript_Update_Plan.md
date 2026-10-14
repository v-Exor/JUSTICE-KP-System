# JUSTICE-KP Manuscript Update Plan

This plan aligns the thesis manuscript with the current implemented JUSTICE-KP system. It is based on the current repository state and the two files in `docs/Manuscript`: `Chapter_1-3.pdf` and `THESIS-MANUSCRIPT.pdf`.

## 1. Main Revision Direction

Rewrite the manuscript from a planned "neuro-symbolic AI stack" into an implemented barangay decision-support prototype.

The current system should be described as:

> JUSTICE-KP is a web-based decision-support system for Katarungang Pambarangay case intake, transcription-assisted documentation, RA 7160 jurisdiction screening, sensitive-case routing, mediation workflow support, KP form packet generation, and thesis validation reporting. The system supports barangay officials but does not replace their legal authority or judgment.

The manuscript should avoid claiming that the current prototype uses technologies that are not implemented in the codebase, such as Experta, CalamanCy, GPT-4o-mini, LoRA training, CNN emotion recognition, OCR, complete offline PWA deployment, or physical template field stamping.

## 2. High-Priority Corrections

Update the draft immediately in these areas:

1. Fill the blank **Specific Objectives** under Chapter 1.
2. Fill the blank **Scope and Limitations of the Research** section.
3. Replace over-claimed implementation descriptions with the actual stack.
4. Reframe performance claims as evaluation targets unless Phase 5 results already prove them.
5. Update Chapter 3 methodology to match the implemented modules and evaluation workflow.
6. Add Phase 4 and Phase 5 evidence to the manuscript because the current system now supports forms and validation.
7. Add limitations about ASR quality, keyword/rule-based detection, human final authority, and ground-truth dependence.

## 3. Claims to Revise or Remove

The existing Chapter 1 draft includes several planned-system claims that should be softened or replaced.

| Existing/Implied Claim | Recommended Revision |
|---|---|
| Uses Experta forward-chaining with 50 rules | Uses a deterministic Python RA 7160 rule engine with traceable rule IDs and explanations |
| Uses CalamanCy NER | Uses regex and rule-based entity extraction for debt amounts, barangay names, dates, categories, threats, and settlement terms |
| Uses GPT-4o-mini for mediation strategies | Uses deterministic mediation suggestion templates based on dispute category and eligibility |
| Uses CNN emotion recognition | Uses lightweight keyword-based emotion/tension scoring |
| Uses Whisper LoRA trained for Laguna dialect | Uses the multilingual `faster-whisper` small model locally with learned transcript corrections |
| Offline PWA with OCR/WebRTC | Uses browser MediaRecorder for recording; no OCR module is currently implemented |
| PostgreSQL auto-forms | Uses SQLite in development and PostgreSQL-ready production config; Phase 4 generates PDF review packets/data attachments |
| 90% time gain, 95% accuracy, 100% VAWC recall as achieved results | Present these as targets or hypotheses unless supported by Phase 5 evaluation results |

## 4. Updated System Scope

Use this as the basis for the **Scope and Limitations** section.

### Suggested Scope Text

This study covers the development and evaluation of JUSTICE-KP, a web-based decision-support prototype for Katarungang Pambarangay workflows. The system supports audio recording, speech-to-text transcription, editable transcript saving, case information intake, sensitive keyword detection, rule-based legal entity extraction, RA 7160 jurisdiction screening, explainable rule tracing, sensitive-case routing, mediation eligibility checking, hearing scheduling, evidence upload with manual notes, KP form recommendation, generated form packet storage, and validation reporting.

The legal scope focuses on barangay-level case screening and workflow support under Republic Act No. 7160, particularly Katarungang Pambarangay coverage, venue, referral, and mediation workflow concerns. The system also includes safety guardrails for VAWC, child abuse, threat, serious injury, and outside-KP cases by recommending referral or manual review instead of automatic mediation.

The intended users are barangay officials, Lupon members, barangay secretaries, and researchers evaluating system outputs. The prototype is intended for thesis evaluation and controlled barangay workflow testing, not for autonomous legal adjudication.

### Suggested Limitations Text

The system is limited to decision support and does not replace the authority, discretion, or legal responsibility of barangay officials. Final case action, referral, settlement approval, and document release remain human decisions.

The transcription output depends on audio quality, microphone conditions, speaker overlap, TagLish clarity, and available local computing resources. Transcription runs through local faster-whisper. Speaker diarization depends on the locally cached pyannote model and Hugging Face configuration; without it, the system uses a fallback speaker assignment.

The legal extraction and sensitive-case detection modules are deterministic and keyword/rule-based. They may miss implied facts, unusual wording, slang, unclear speech, spelling variation, or legal details not entered in the transcript or intake form. The emotion/tension score is also keyword-based and should not be treated as a clinical or psychological assessment.

The Phase 4 form generator produces review packets and data attachments based on available case information. It does not guarantee complete physical field stamping on every official template, and all generated forms require official review before use.

The Phase 5 evaluation dashboard depends on reviewed ground-truth labels. Accuracy, recall, form correctness, compliance, and time-saving results should only be reported after validation cases are imported, labeled, evaluated, and reviewed.

## 5. Updated Research Objectives

Replace the blank specific objectives with objectives that match the current system.

### General Objective

The general objective of this study is to develop and evaluate JUSTICE-KP, a web-based decision-support system that assists barangay officials in transcription-assisted case intake, RA 7160 jurisdiction screening, sensitive-case routing, mediation workflow support, KP form packet generation, and validation reporting for Katarungang Pambarangay cases.

### Specific Objectives

1. To design and implement an audio recording and transcription workflow that allows barangay hearing audio to be converted into editable speaker-labeled transcripts.
2. To develop deterministic case analysis modules for sensitive keyword detection, rule-based legal entity extraction, RA 7160 jurisdiction screening, and explainable rule tracing.
3. To implement Phase 3 case workflow support for sensitive-case routing, referral recording, mediation eligibility checking, mediation suggestion generation, hearing scheduling, evidence upload, and official decision logging.
4. To implement Phase 4 KP form support through a form template registry, case-to-form recommendation, required-field validation, generated packet storage, and downloadable generated form review packets.
5. To implement Phase 5 validation tools for ground-truth entry, system-output evaluation, compliance review, CSV/report export, anonymized export, and experiment run documentation.
6. To evaluate the prototype using functional tests and validation metrics such as jurisdiction accuracy, sensitive-case accuracy, referral accuracy, mediation accuracy, keyword precision/recall, form accuracy, compliance score, and processing-time comparison.

## 6. Chapter-by-Chapter Update Plan

### Chapter 1: Introduction and Its Background

Update Chapter 1 to introduce the actual system and the practical problem it addresses.

Recommended changes:

1. Keep the discussion of manual KP workflow problems: transcription delay, jurisdiction screening errors, VAWC referral risks, repeated form encoding, and lack of traceable reasoning.
2. Replace claims about unimplemented AI components with implemented modules.
3. Present JUSTICE-KP as a practical decision-support system rather than an autonomous legal AI system.
4. Fill the blank specific objectives using the objectives above.
5. Fill Scope and Limitations using the suggested scope and limitations above.
6. Keep Significance of the Research, but reduce unsupported nationwide numerical claims unless cited and validated.

Suggested Chapter 1 framing:

> JUSTICE-KP addresses documentation and decision-support gaps in barangay justice workflows by combining transcription-assisted intake, deterministic RA 7160 screening, explainable rule traces, workflow routing, form packet generation, and validation metrics. The system is designed to assist barangay personnel while preserving human authority over final case decisions.

### Chapter 2: Review of Literatures

Keep the literature review, but revise the synthesis so it matches the implemented design.

Recommended structure:

1. Speech-to-text systems for local language and TagLish documentation.
2. Barangay e-blotter and local government information systems.
3. Rule-based legal expert systems and explainable legal decision support.
4. Sensitive-case routing and VAWC referral concerns.
5. Digital form generation and workflow automation.
6. Software validation, ISO 25010, and evaluation metrics.
7. Synthesis showing why the implemented hybrid approach was selected.

Important correction:

Do not make the synthesis depend on ML components that are not implemented. The strongest current contribution is the integration of ASR-assisted documentation, deterministic RA 7160 screening, explainable traces, KP workflow support, form packet generation, and validation reporting.

### Chapter 3: Research Methodology

The manuscript guide requires Chapter 3 to include research design, locale, applied concepts, algorithm analysis, data collection, model/data generation, system development methodology, software tools, architecture, and testing.

Recommended Chapter 3 sections:

1. **Research Design**
   - Use developmental research plus experimental/evaluation design.
   - Describe prototype development and system-output evaluation using Phase 5.

2. **Locale of the Study**
   - Describe the barangay/KP setting where cases or test workflows are evaluated.
   - If final respondents are not yet fixed, state the intended locale and evaluator roles carefully.

3. **Applied Concepts and Techniques**
   - Speech-to-text transcription.
   - Speaker diarization.
   - Rule-based text processing.
   - Deterministic legal rule evaluation.
   - Explainable AI through rule traces.
   - Workflow automation.
   - Form validation.
   - Evaluation metrics.

4. **Algorithm Analysis**
   - Include pseudocode for:
     - transcription and transcript normalization;
     - sensitive keyword detection;
     - RA 7160 rule evaluation;
     - Phase 3 routing;
     - Phase 4 form recommendation;
     - Phase 5 evaluation metrics.

5. **Data Collection Methods**
   - Case transcripts or test transcripts.
   - Case information fields.
   - Ground-truth labels.
   - Manual and system processing time.
   - Compliance review signals.

6. **Data Model Generation**
   - Describe database tables or entities:
     - transcripts;
     - case information;
     - case analysis;
     - XAI traces;
     - Phase 3 routes/referrals/hearings/evidence/official decisions;
     - Phase 4 packets/forms;
     - Phase 5 validation/ground truth/evaluation/compliance/experiment runs.

7. **System Development Methodology**
   - Use iterative/incremental development by phase:
     - Phase 1 transcription;
     - Phase 2 case analysis;
     - Phase 3 workflow routing;
     - Phase 4 forms;
     - Phase 5 validation;
     - production hardening.

8. **Software Tools Used**
   - Frontend: Next.js, React, TypeScript, Tailwind CSS, Axios, Browser MediaRecorder API, jsPDF.
   - Backend: FastAPI, SQLAlchemy, Pydantic, SQLite, PostgreSQL-ready production config.
   - ASR: fully local faster-whisper with learned correction normalization.
   - Diarization: pyannote optional.
   - Testing: Python unittest, TypeScript type checking.
   - Deployment: Docker files and production environment checks.

9. **System Architecture**
   - Present a layered architecture:
     - user interface layer;
     - API layer;
     - transcription layer;
     - analysis/rule layer;
     - workflow layer;
     - form generation layer;
     - validation/reporting layer;
     - persistence/security layer.

10. **Software Testing**
    - Backend unit tests currently cover:
      - RA 7160 rule engine;
      - Phase 3 workflow services;
      - Phase 4 form services;
      - Phase 5 validation services;
      - KP case importer;
      - production hardening.
    - Frontend validation should include TypeScript checking and manual workflow testing.

### Chapter 4: Results and Discussion

Use the current Phase 5 system as the backbone for Chapter 4 evidence.

Recommended result tables:

1. Functional test results per phase.
2. RA 7160 jurisdiction accuracy.
3. Sensitive-case detection accuracy.
4. Referral route accuracy.
5. Mediation eligibility accuracy.
6. Keyword precision and recall.
7. Form recommendation/generation accuracy.
8. Compliance review score.
9. Manual vs system processing time.
10. Error case analysis from Phase 5 exported report.

Important:

Only report measured values after importing cases, entering ground truth, running evaluation, and exporting reports from Phase 5. Until then, describe expected metrics and evaluation design, not final results.

### Chapter 5: Summary, Conclusions, and Recommendations

Write Chapter 5 after Phase 5 results are available.

Recommended summary points:

1. The system successfully integrated transcription-assisted documentation and deterministic KP screening.
2. Rule traces improved transparency of system recommendations.
3. Phase 3 organized sensitive routing, referral, mediation, evidence, hearing, and official decision workflows.
4. Phase 4 reduced repeated form preparation through form recommendations and generated review packets.
5. Phase 5 enabled thesis-ready evaluation through ground truth, metrics, compliance review, and exports.

Recommended recommendations:

1. Improve TagLish ASR accuracy with larger datasets or local adaptation.
2. Expand legal coverage beyond the currently encoded RA 7160/KP screening rules.
3. Add stronger template field stamping for official KP PDFs.
4. Add richer NLP or supervised classifiers after enough validated data is collected.
5. Conduct broader field testing across more barangays.
6. Strengthen privacy, consent, retention, and deployment controls for real operational use.

## 7. Figures and Tables to Add

### Recommended Figures

1. JUSTICE-KP System Architecture.
2. End-to-End Workflow from Recording to Validation.
3. Phase 2 RA 7160 Rule Evaluation Flow.
4. Phase 3 Sensitive Routing and Mediation Workflow.
5. Phase 4 Form Recommendation and Packet Generation Flow.
6. Phase 5 Validation and Metrics Flow.

### Recommended Tables

1. Software Tools Used.
2. System Modules and Functions.
3. Database Entity Summary.
4. RA 7160 Rule Categories and Outputs.
5. Phase 3 Routing Categories.
6. KP Form Registry and Usage Conditions.
7. Evaluation Metrics and Formulas.
8. Functional Test Cases.
9. Limitations and Mitigation Strategies.

Follow the manuscript guide: table titles above tables, figures captions below figures, Times New Roman 12, body text double-spaced, and APA 7 references.

## 8. Current Implemented Modules to Cite in the Manuscript

### Backend Modules

| File | Manuscript Description |
|---|---|
| `backend/transcribe.py` | Local Whisper transcription fallback |
| `backend/transcribe.py` | Local faster-whisper ASR integration |
| `backend/diarization.py` | Optional pyannote speaker diarization |
| `backend/keyword_detector.py` | Sensitive keyword detection |
| `backend/legal_ner.py` | Rule-based legal entity extraction |
| `backend/rule_engine.py` | Deterministic RA 7160 jurisdiction engine |
| `backend/xai_trace.py` | Explainable rule trace generation |
| `backend/phase3_services.py` | Routing, referral, mediation, hearing, evidence, emotion/tension, dashboard |
| `backend/phase4_services.py` | KP form registry, recommendation, validation, generated packets |
| `backend/phase5_services.py` | Validation dataset, metrics, compliance, exports |
| `backend/auth_service.py` | Authentication and role-based access |
| `backend/backup_service.py` | Backup and restore support |
| `backend/models.py` | Database models |
| `backend/main.py` | FastAPI endpoints |

### Frontend Modules

| File | Manuscript Description |
|---|---|
| `frontend/components/JusticeDashboard.tsx` | Main dashboard and workflow interface |
| `frontend/components/Recorder.tsx` | Recording and transcript workflow |
| `frontend/components/CaseAnalysis.tsx` | Case information intake and Phase 2 analysis |
| `frontend/components/Phase3DashboardPage.tsx` | Phase 3 workflow, Phase 4 forms, official decisions |
| `frontend/components/XAITracePanel.tsx` | Explainable rule trace display |

## 9. Evaluation Metrics to Use

The Phase 5 system supports the following thesis-ready metrics:

| Metric | Meaning |
|---|---|
| Overall accuracy | Whether all comparable system outputs match ground truth |
| Jurisdiction accuracy | Match between expected and actual jurisdiction decision |
| Sensitive-case accuracy | Match between expected and detected sensitive-case status |
| Referral accuracy | Match between expected and actual referral route |
| Mediation accuracy | Match between expected and actual mediation eligibility |
| Form recommendation accuracy | Match between expected and generated/recommended form IDs |
| Keyword precision | Fraction of detected keywords that are expected |
| Keyword recall | Fraction of expected keywords detected by the system |
| Form accuracy percentage | Required Phase 4 fields completed versus missing |
| Compliance score | Consent, anonymization, official decision, reviewed forms, audit trail, and sensitive referral checks |
| Time saved percentage | Manual processing time compared with system processing time |

## 10. Recommended Writing Sequence

Use this order to revise efficiently:

1. Update Chapter 1 objectives, scope, limitations, and system description.
2. Revise Chapter 2 synthesis to match the actual implemented system.
3. Rewrite Chapter 3 around the implemented modules, architecture, data model, and testing.
4. Populate Phase 5 validation cases and export metrics.
5. Write Chapter 4 using exported Phase 5 results.
6. Write Chapter 5 only after Chapter 4 metrics are final.
7. Add appendices:
   - screenshots;
   - workflow diagrams;
   - test results;
   - validation instruments;
   - sample anonymized reports;
   - user manual;
   - system architecture and data dictionary.

## 11. Appendix Checklist

The manuscript guide recommends these appendix materials. For JUSTICE-KP, include:

1. Planning and requirement analysis.
2. Current and proposed process flow.
3. Storyboard or workflow screenshots.
4. Use case diagram.
5. System architecture.
6. Data flow diagram.
7. Data dictionary.
8. Input/output/report screenshots.
9. Testing and evaluation instruments.
10. Implementation plan.
11. User manual.
12. Communication letters, acceptance documents, or evaluation approvals if available.

## 12. Final Reminder

The safest thesis positioning is:

> JUSTICE-KP is an implemented, explainable, rule-based decision-support prototype for KP workflow assistance and evaluation, with optional ASR services and human-in-the-loop official control.

Avoid presenting it as:

> A fully autonomous AI legal adjudicator, trained legal language model, complete CNN emotion recognizer, or production-certified government deployment.
