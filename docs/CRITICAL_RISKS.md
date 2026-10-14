# Critical Risks

| Risk | What could happen | Recommended control |
|---|---|---|
| Incorrect ASR transcript | Names, dates, money, threats, or statements may be transcribed incorrectly. | Always retain raw audio, show raw and edited transcripts, and require human review. |
| Wrong speaker attribution | Pyannote may separate voices correctly but assign the wrong role; keyword-based role detection can also mislabel quoted titles. | Allow manual speaker correction and report diarization confidence separately. |
| Incorrect KP decision | Incomplete facts or inaccurate transcripts may cause the rule engine to select the wrong route. | Treat output as a recommendation requiring official confirmation. |
| Sensitive-data exposure | Recordings contain personal, legal, medical, family, and possibly child-protection information. | Use encryption, access controls, retention rules, audit logs, and secure backups. |
| Evidence integrity | Audio or transcripts could be edited without proving what changed. | Preserve immutable original audio, file hashes, timestamps, editor identity, and full revision history. |
| Data loss | A single computer, database corruption, disk failure, or accidental deletion could remove cases. | Use automatic encrypted backups and regularly test restoration. |
| No reliable source-code rollback | The current project folder is not functioning as a valid Git repository. | Use Git checkpoints before changing workflows or database behavior. |

## Risks During the Oral Defense

The most likely presentation risks are:

- Backend not running
- Frontend and backend using different hostnames
- First Whisper/pyannote model load taking several minutes
- Microphone permission denied
- Poor room audio
- Workflow draft containing stale data
- A button disabled because an earlier requirement was not saved
- Database containing test duplicates
- Internet-dependent resources unexpectedly unavailable

## Before the Defense

1. Freeze major feature changes.
2. Create a Git checkpoint.
3. Back up the database, recordings, transcripts, and forms.
4. Prepare two known working demonstration cases.
5. Test the entire workflow from recording through validation.
6. Use `127.0.0.1` consistently.
7. Preload the ASR and diarization models.
8. Bring backup recordings and screenshots.
9. Clearly state that officials confirm all AI recommendations.
10. Include limitations in the presentation instead of claiming perfect accuracy.

Your immediate priorities should be data integrity, workflow consistency, Git/version control, backup restoration, validation quality, and mandatory human confirmation.
