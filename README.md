# AI Job Assistant

A local Python command-line project for comparing your skills with pasted job
descriptions and suggesting learning steps. Phase 1B adds local profiles, SQLite
storage and reviewed PDF/DOCX/TXT CV imports. Phase 1C adds structured, evidence-based
CV analysis. All default workflows run offline without an API key. Optional OpenAI
assistance requires explicit consent and can incur API charges.
Phase 2A adds bounded job-description entry/import and explainable offline matching
against an approved CV, with no automated scraping or graphical interface.
Phase 2B adds separately consented, bounded AI interpretations with mandatory local
evidence validation; offline results remain authoritative.
Phase 3A adds local application tracking, durable status history and explicit
CV/comparison provenance links, using a transactional schema version 2 migration.
Phase 3B adds a professional local Streamlit tracking dashboard, follow-up dates and
action completion, with an additive schema version 3 migration.
Phase 4A adds offline role-specific interview practice, STAR guidance, saved answer
attempts and evidence-aware coaching, with a transactional schema version 4 migration.
Phase 4B adds optional consent-based AI coaching and the Interview Practice dashboard.
Offline practice remains the default; Phase 4B needs no additional database migration.
Phase 5A adds offline personalised skills roadmaps and milestone progress, using an
additive schema version 5 migration.

## Setup and run

Use Python 3.10+ for the CLI and Python 3.11+ for the dashboard. Phase 5B was
validated on macOS arm64 with Python 3.14.5. See the release-review section for
dependency security findings and platform limitations before installation.
From the project directory on macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip --isolated install --index-url https://pypi.org/simple --upgrade "pip>=26.2"
python -m pip install -r requirements.txt
python main.py
```

On Windows, create the environment with `py -m venv .venv`, activate with
`.venv\Scripts\Activate.ps1` in PowerShell, then run the pip upgrade/install commands
above before `python main.py`. Do not use a system-wide install.
The original job analyser still uses only the standard library; the requirements
add `pypdf` and `python-docx` for document imports. SQLite ships with Python.

For the visual dashboard, install its optional dependency set and launch locally:

```sh
python -m pip install -r requirements-dashboard.txt
python -m job_assistant.dashboard_launcher
```

Open `http://127.0.0.1:8501` in your browser. Keep the terminal running; Ctrl+C stops
the dashboard. See the Phase 3B section for privacy, custom databases and UI details.
The CLI still runs with `python main.py` and does not require Streamlit.

1. Enter a name (used only for the greeting).
2. Enter comma-separated skills, e.g. `Python, ML, SQL`. Type `none` if you
   have no skills to enter yet. Blank input and comma-only input are rejected.
3. Paste a one-line job description.
4. Review detected, matching and missing skills, the coverage score and roadmap.
5. Enter `yes`/`y` to analyse another job or `no`/`n` to finish.

For multiline descriptions, use:

```sh
python main.py --multiline
```

A blank line ends the description. For descriptions containing blank lines,
paste paragraphs without intervening blank lines. Ctrl+C or end-of-input exits
cleanly; an unfinished description is not saved.

## Reports and privacy

The default report is `job_analysis.txt` beside `main.py`, regardless of the
directory from which you launch the application. The first save creates it.
Existing UTF-8 report content is retained and new reports are numbered. To use
a different file, including for a synthetic demonstration:

```sh
python main.py --report local_data/demo.txt
```

Relative custom paths are relative to your current working directory. Parent
directories are created. A complete UTF-8 replacement is written to a temporary
file in the destination directory before an atomic replacement. A failed write
or replacement leaves the previous report intact. Unreadable or invalid UTF-8
files are not silently reset. Errors are shown in the terminal; check the path,
permissions and available disk space. Exit status is 1 if any save failed,
0 after a normal successful session, and 130 after interruption.

## Local profiles and CV imports

Running `python main.py` keeps the original job comparison workflow. CV commands
are explicit opt-in operations; the job analyser does not automatically create a
database, read documents or change your saved profile.

```sh
python main.py profile-create
python main.py profile-list
python main.py cv-import /path/to/your-chosen-cv.pdf --profile 1
python main.py cv-list
python main.py cv-list --profile 1
python main.py cv-show 1
python main.py cv-show 1 --source
python main.py cv-delete 1
```

Use the profile/CV IDs printed by the application rather than assuming they are 1.
Profile creation reviews the name and normalised skills before confirmation.
Import requires an existing profile. It displays the extracted source units and
warnings, then lets you enter a unit number to correct that unit's text. Finish a
multiline correction with `/done` on its own line. Blank replacement text clears
that unit. Enter `done` to see the complete corrected text and confirm the save,
or `cancel` to discard the import. An all-blank or oversized result cannot be
saved. Cancellation or interruption before confirmation saves no CV content.
The CV title is editable before review. Original extraction remains separate
from reviewed corrections, so evidence can be traced back to its source unit.

`cv-list` shows metadata only; `cv-show` intentionally displays reviewed text.
`--source` displays original extracted text. Terminal controls in document text
are escaped. `cv-delete` requires confirmation and removes the CV metadata plus
all original and reviewed source units, retaining the associated profile.
Original PDF/DOCX/TXT files are never changed, copied into the application or
deleted. Profile edits and profile deletion are not yet exposed in the CLI.

The default database is `local_data/assistant.sqlite3` beside the project, not
relative to your launch directory. To use an isolated database, put the global
option **before** the command:

```sh
python main.py --database local_data/demo.sqlite3 profile-create
python main.py --database local_data/demo.sqlite3 cv-list
```

The CV tables are `profiles`, `cvs` (metadata, SHA-256 digest, extractor version,
warnings and review timestamp) and `cv_segments` (ordered source references,
original text and reviewed text). Only the basename of an imported file is saved,
not its full filesystem path. Text remains sensitive even when filenames are omitted.
New databases use schema version 5 (`PRAGMA user_version`) and an application ID.
Version 1/2/3/4 databases migrate transactionally as described below.
Initialization and CV saves are transactional; deletion cascades to source units.
Foreign keys are enabled on every connection. Unknown versions, incomplete tables
and unrelated databases are rejected, not reset. Only explicitly implemented migrations
are applied; there is no destructive automatic reset. All user SQL values are bound
parameters. Errors avoid parser exception details and document content.

New database files use owner-only permissions on POSIX systems; new data directories
request owner-only access. Existing file/directory permissions are not changed.
SQLite secure deletion is enabled, but filesystem snapshots, backups and storage
hardware can retain historical data. This is local plaintext storage, not encryption
or a guarantee of forensic erasure. Keep backups private; close the app before
copying a database for backup. Custom database filenames and SQLite sidecars are
ignored by Git. Import, storage and offline analysis never send CV content over the
network. No document content is written to application logs; review/show/analysis
intentionally display excerpts in your terminal, whose history may retain them.
The separate OpenAI opt-in below can send approved reviewed text externally.

## Evidence-based CV analysis (Phase 1C)

Analyse an already imported and approved CV by its ID:

```sh
python main.py cv-analyse 1
python main.py cv-analyse 1 --output local_data/cv_analysis_1.txt
python main.py --database local_data/demo.sqlite3 cv-analyse 1
```

Offline analysis is the default, needs no API key and adds no dependencies. It uses
approved **reviewed text**, rather than silently reverting corrections to the original
extraction. It does not read another CV, the original file or profile skills to fill
gaps. The report groups skills, experience, education, projects and achievements,
and separates:

- **Explicitly supported wording:** what the CV actually says, with exact excerpts.
  Skill mentions are not proof of competence; statements under a heading remain
  self-reported claims, not independently verified facts.
- **Uncertain interpretations:** aspirational/negative/limited skill wording and
  unlabelled activities whose employment or education context is unclear.
- **Improvement suggestions:** conditional actions for clearer wording, contribution,
  structure, dates and genuine outcomes. Never invent a metric, qualification or job.
- **Cannot be determined:** missing recognisable evidence, proficiency, total years,
  accuracy, visual/ATS compatibility and hiring probability. Unrecognised evidence
  does not mean the applicant lacks the experience or skill.

Each evidence item includes its stored source-unit position, original page/paragraph/
line reference, and zero-based start/end offsets into that unit's reviewed text.
The end offset is exclusive. Corrected source units are marked; these quotes may
differ from the original extraction available through `cv-show ID --source`.
Reports include the approval timestamp, analysis-rules version and a digest of the
reviewed text and references for reproducibility. The digest is an identifier, not
encryption. Extraction warnings remain visible.

The offline classifier recognises common section headings (including case, bullets
and full-width heading variants), known skill terms, action wording and outcome
claims. It is a conservative rule-based baseline, not semantic understanding or a
complete CV parser. Unusual headings, dates, synonyms and complex layouts can be
missed or misclassified. Dates are quoted, not used to infer employment duration.
No skills-proficiency or overall CV score is produced. Review classifications before
using them in applications. Findings are limited to 20 per category, citations to
300 characters, and suggestions to 20 offline items; overflow is noted. Input limits
remain 200,000 reviewed characters and 2,000 units. Instruction-like source lines
are treated as document data and excluded from findings; this heuristic is not a
complete prompt-injection detector.

The terminal report is always shown first. `--output` offers an explicit yes/no save
after review. It writes the displayed report as private UTF-8 text, atomically, and
**never overwrites an existing file or symbolic link**. Choose a new path for each
report; the existing job-analysis history is unaffected. Filesystems without atomic
hard-link support return a clear save error. Reports contain personal excerpts:
keep them under ignored `local_data/`, protect backups, and avoid sharing them
accidentally. Deleting a CV from SQLite does not delete separately exported reports.
Analysis does not alter imported content. Phase 3A storage initializes/migrates to
the current schema version before database operations.

## Explainable job comparison (Phase 2A)

Compare a selected approved CV with entered or explicitly imported job text:

```sh
python main.py job-compare 1
python main.py job-compare 1 --job-file /path/to/job-description.txt
python main.py job-compare 1 --job-file /path/to/job-description.pdf --output local_data/job_comparison_1.txt
python main.py --database local_data/demo.sqlite3 job-compare 1 --job-file /path/to/job-description.docx
```

Replace `1` with your imported CV ID. Without `--job-file`, enter multiple lines,
including blank lines, and finish with `/done` on its own line. This workflow is
offline by default, even if an OpenAI API key is present. Phase 2B assistance requires
the separate flags and consent described below. It never fetches document URLs or
scrapes job sites. Only the explicitly selected document and CV are read.

TXT/PDF/DOCX job imports reuse the Phase 1B extraction, type checking, encryption
rejection, file-size limits and warnings. Additional job limits are 20,000 extracted
characters, 300 source units, 1,000 characters per line and 100 generated requirement
items (including unrecognised criteria/context). Limits are checked without silent
truncation; shorten or split the description when necessary. Blank/headings-only
input, control characters and invalid files produce clear errors.

The report shows **essential**, **desirable** and **unclear** priorities separately.
Recognised headings establish a priority; inline `required`, `must`, `preferred`,
`optional` and similar markers can override it. Unknown colon headings and common
non-requirement section headings reset inherited priority to unclear. Contrasting
clauses are separated, and conflicting markers/ambiguous scope require review.
An unclear priority is not automatically an essential requirement.

Matching outcomes are independent of priority:

| Outcome | Meaning |
| --- | --- |
| Matched | Positive approved CV wording supports a recognised skill mention; a self-reported claim, not verified ability |
| Missing | No supporting reviewed-CV claim found, or explicit negative wording without positive support; not proof the person lacks it |
| Uncertain | Tentative/contradictory/third-party wording, related technology, unclear grammar, incomplete practical evidence or qualifications needing review |
| Unsupported | Unknown technology, qualification, task or other context the rules cannot assess; retained rather than discarded |
| Excluded | Clearly negated/prohibited job skill or employer-provided training context; not counted as a positive candidate requirement |

Both sides are cited: original job page/paragraph/line references and exact excerpts,
plus approved CV excerpts with reviewed-text offsets and correction markers. A missing
or unsupported item may have no relevant CV excerpt; the report states that rather
than inventing evidence. Report hashes identify the reviewed CV and job text used.
Phase 1C analysis validates approval and provides provenance/extraction warnings.
Matching scans **all reviewed CV text**, so its evidence is not restricted to Phase
1C's 20-per-category display limit. Profile skill lists and original uncorrected
extraction do not fill gaps in the approved CV.

Specific safeguards include:

- Common negations such as `No Python required` or `Python not required` do not
  become positive requirements. Double negatives and mixed scope are conservative.
- CV aspirations, beginner wording, missing context, contradictions and common negative
  contractions are distinguished from positive mentions. Emails and URL paths are not
  skill evidence. `machine-learning` is not mistaken for aspirational "learning".
- Aliases such as ML, JS and REST APIs use word boundaries and longer-term precedence.
  PostgreSQL does not automatically match SQL in either direction; related evidence
  is uncertain. Generic API knowledge does not prove REST API knowledge. Continuous
  integration does not establish CI/CD; an explicit CI/CD mention can support CI.
- `Python or JavaScript` is a grouped alternative. Unknown alternatives and mixed
  AND/OR wording remain uncertain. Unrecognised context alongside recognised skills
  creates a visible unsupported item; it cannot silently inflate a score.
- A skill list alone does not establish practical experience. Activity wording can
  support a self-reported practical claim, but commercial context, advanced proficiency,
  certifications and numeric or spelled-out durations require human review. No years,
  degrees or qualifications are inferred or invented.

There is **no overall suitability score or hiring probability**. Counts describe
generated items, which may include multiple skills or unknown context from one clause;
they are not percentages of all job requirements. Review source wording yourself.

`--output` offers a yes/no save after showing the report and reuses the atomic,
owner-only, non-overwriting report writer. No file is saved without confirmation.
Comparison exports include personal CV excerpts; keep them under ignored `local_data/`
and protect backups. Jobs/comparisons are otherwise held in memory, not added to SQLite.
Imported CVs, existing job reports and earlier commands are retained; Phase 3A adds
the versioned storage migration without rewriting CV rows.
Deleting a CV does not remove separately exported comparisons. No new dependencies
are required beyond those already used for document extraction.

### Evaluation and limitations

`tests/fixtures/job_matching_cases.json` contains 23 manually labelled synthetic cases.
Each checks one designated requirement outcome, including aliases, hyphenation,
negative wording, OR alternatives, email false positives, injection text, duration,
practical evidence and specific-versus-general technology claims. Seven targets are
positive matches and sixteen are non-matches (missing/uncertain/unsupported/excluded).
The automated evaluation checks exact outcomes and false-positive/false-negative
match counts. This is a regression set, not a representative benchmark or evidence
of real-world accuracy. Additional tests cover extraction/limits, evidence offsets,
negation scope, CLI entry/export, approved-data preservation and previous workflows.

This remains a deterministic English-language baseline. It cannot fully parse arbitrary
grammar, all abbreviations, cross-line relationships, alternative group nesting,
unusual headings, eligibility, salaries, degrees or employment histories. Unsupported
free text includes both genuine unknown criteria and ordinary contextual prose.
Repeated requirements are retained as separate items. CV clauses longer than 300
characters are uncertain rather than confidently classified. Complex negation can
still be misclassified; shortening and clarifying wording helps. Abbreviation mappings
assume a technical-job context and may be ambiguous in other fields. A matched skill
mention does not establish competence or satisfy additional unsupported context.
The legacy `python main.py` scorer is preserved and does not gain these new safeguards;
use `job-compare` for Phase 2A evidence-based comparison.

## Optional AI-enhanced job matching (Phase 2B)

The original `job-compare` behaviour is unchanged when `--openai` is absent. To offer
AI interpretations, select a Responses API model that supports strict structured
outputs, provide its current standard input/output token prices in USD per million
tokens, and optionally lower the estimated-cost guard:

```sh
python main.py job-compare 1 --job-file /path/to/job.txt --openai \
  --model YOUR_MODEL_ID \
  --input-usd-per-million INPUT_RATE \
  --output-usd-per-million OUTPUT_RATE \
  --max-estimated-usd 0.25 \
  --output local_data/job_comparison_ai_1.txt
```

Replace the model/rate placeholders with actual values from
[current OpenAI pricing](https://developers.openai.com/api/docs/pricing); the program
does not fetch prices or assume account/model availability. Prices are user-supplied
and are **not provider-verified**. Both rates must be finite decimals from 0.000001
to 1,000,000 USD per million tokens. The estimated budget must be 0.000001–100 USD;
its default is 0.25 USD. Invalid/missing prices or a model, oversized inputs, stale
source snapshots and over-budget estimates skip the request and retain offline results.
Set `OPENAI_API_KEY` through your environment/secret manager as described below.

The offline report appears first. Before any external request, warnings explain:

- The selected reviewed CV and job text are sent to `api.openai.com`; personal and
  confidential information inside them is **not automatically anonymised**. Source
  files, original uncorrected extraction, profile details, filenames, references,
  database IDs and unrelated CVs are excluded from the payload. Unit positions and
  parsed requirement metadata are included to anchor evidence.
- The estimated cost uses `(encoded request bytes + 1,024 framing allowance)` as a
  conservative input-token proxy, plus the maximum 2,400 output tokens, multiplied
  by the supplied rates. This is a heuristic, not exact tokenization or a guaranteed
  upper bound on billing. It is not a provider-enforced spending cap. Check account
  spend controls; cached/special pricing and pricing changes are not resolved here.
- One request is permitted per consent, without retries, redirects, tools, lookups or
  automatic follow-ups. A failed or rejected response may still be charged.
- `store=false` is requested; this does **not** guarantee zero retention. Provider
  abuse monitoring and account-specific controls still apply. See
  [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data).

Only typing the exact word **SEND** after these warnings authorises transmission.
The flag, an API key, `yes`, `send` or an empty response do not provide consent.
The app neither loads `.env` files automatically nor reads the API key in offline
mode. Cost metadata is included in an optionally exported report, not application logs.

| AI matching limit | Value |
| --- | --- |
| CV input | 12,000 reviewed characters and 200 units |
| Job input | 8,000 characters and 100 units |
| Encoded request / response | 96,000 / 65,536 bytes |
| Output | 2,400 tokens; at most 12 interpretation items |
| Evidence | Exact unit IDs and offsets; quotes of 1–300 characters |
| Timeout | 30 seconds per socket operation, not a wall-clock deadline |
| Calls | One verified HTTPS request; no retries or tools |

Limits reject rather than silently truncate documents. Large or complex inputs
can still be compared offline using Phase 2A limits.

### Mandatory validation and interpretation boundaries

The model can select existing requirement IDs, a known skill, an interpretation kind
(abbreviation, related evidence or complex wording), a proposed outcome, and exact
job/CV spans. It cannot supply free-form factual summaries, create requirements,
change priorities, update the CV, invent a skill name or modify offline conclusions.
Requests use [strict structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Local code independently checks all field names/types/enums/counts, completed
response status, unique requirement IDs and exact quotes/offsets in both documents.
Forged citations, out-of-requirement spans, duplicate JSON keys, instruction-bearing
source lines, extra factual fields and malformed/refused/incomplete responses fail
validation. The entire malformed batch is discarded; no partial acceptance occurs.

For semantic validation, the app scans the full approved CV, including negative,
tentative and contradictory claims. A match must cite an independently positive
source clause and the relevant skill in the job excerpt. Practical-experience
matches must cite an activity, not merely a skill list elsewhere. Citing a weak,
third-party or contact-details fragment cannot borrow strength from a different CV
passage. Missing-evidence proposals are checked against the full CV, not just the
model's chosen excerpts. There is still no independent qualification verification.

AI abbreviation interpretations may use only this fixed local map:

| Abbreviation | Interpreted skill |
| --- | --- |
| Py | Python |
| K8s | Kubernetes |
| sklearn | scikit-learn |
| TF | TensorFlow |

For example, `K8s required` versus `Skills: Kubernetes` remains unsupported in the
unchanged Phase 2A baseline, but can receive a separate **evidence-validated AI
interpretation** using this map. Re-parsing the expanded job excerpt must not hide
unknown compound criteria or qualification constraints. Negative/contradictory
alias evidence is retained. The map assumes a technical context; verify ambiguous
abbreviations yourself. Other novel equivalences or complex qualifications cannot
be promoted to matches. Duration, advanced proficiency, degrees and certification
continue to require review. Unrecognised contextual prose is not proof of eligibility.

### Reports, failures and limitations

Every baseline conclusion is labelled `offline rules`. A separate AI supplement shows
proposed and validated outcomes, exact job/CV citations, model ID and provenance:

- **Evidence-validated matches:** citations and local rules passed; self-reported CV
  wording only. “Validated” does not mean independently verified competence.
- **Missing evidence:** local scanning also finds no positive support; not a claim
  that the person lacks the skill.
- **Uncertain interpretations:** manual review remains necessary.
- **Unsupported model claims / review items:** the proposal was not upheld locally,
  or the model explicitly left it unsupported. Raw factual inventions are never used.

The supplement covers at most 12 selected items. It does not change baseline counts,
priorities or any existing suitability score, and introduces no hiring probability.
It may suggest attention to complex wording, but does not resolve arbitrary semantics
that the deterministic validator cannot check. This conservative boundary can reject
valid interpretations. Correct citations alone do not establish semantic truth, and
instruction detection is heuristic, not a guarantee that a model ignored an attack.

Timeouts, authentication/rate-limit/provider errors, missing keys and invalid output
are reported safely without response bodies or credentials. The complete offline
comparison remains available and can be saved; successful fallback exits with status
0. Semantic rejections with structurally valid evidence are displayed explicitly as
unsupported model conclusions; malformed responses fall back with no AI conclusions.
Export retains the existing confirmation, owner-only atomic save and no-overwrite
behaviour. AI matching does not change stored CV data or previous reports. No new runtime
dependencies are needed; both AI features share the bounded HTTPS transport.

Tests use mocked provider responses and synthetic documents only. They cover schema
errors, forged and cherry-picked citations, contradictory evidence, malicious document
instructions, unsafe qualifications, consent/cost gates, provider failures and report
preservation. No live paid calls or private CVs were used, and no claim is made about
live model accuracy or improved real-world matching performance. The Phase 2A
23-case regression evaluation remains an offline baseline.

## Local application tracking (Phase 3A)

Application commands are completely local: no scraping, automatic submissions,
network calls or AI service is involved. Applications need not have a CV link.

```sh
python main.py application-create --company "Example Ltd" --role "AI Apprentice" \
  --job-url "https://example.invalid/jobs/123" --deadline 2099-12-31 \
  --next-action "Review the role and prepare an application"
python main.py application-list
python main.py application-show 1
python main.py application-update 1 --status applied --application-date 2020-01-02
python main.py application-update 1 --status interviewing --next-action "Practise interview answers"
python main.py application-list --status interviewing --company Example
python main.py application-delete 1
```

These are illustrative values/dates; use the IDs printed by your own commands and
your actual application date. Create, update and delete show the record/proposed
values and ask for confirmation before writing. Ctrl+C/end-of-input during review
saves no incomplete change. Read/list operations do not require confirmation.
Database initialization/migration can still occur when a cancelled command opens
the database, but no application is created or changed by cancellation.

### Fields, dates and status history

Each record stores company and role (required; 1–200 characters each), optional HTTP(S)
job URL (up to 2,048 characters), application date, status, deadline, notes (up to
10,000 characters), next action (up to 1,000 characters), UTC creation/update timestamps
and a revision counter. URLs must have a host and cannot contain credentials,
whitespace or backslashes; they are stored as text and never fetched. A URL's query
can still contain private identifiers, so check entered URLs before exporting.
Unsupported terminal controls are rejected; displayed text is escaped where needed.

Supported statuses are `saved`, `applied`, `interviewing`, `offered`, `rejected` and
`withdrawn`. Initial status is `saved` unless explicitly supplied. Every actual status
change appends an event with previous/new status and a UTC timestamp in
`application_status_history`; creation adds the initial event. Repeating the current
status does not add a duplicate. All changes between these known statuses are allowed,
including corrections, reapplications and moving backward. There is no forced pipeline
or inferred status/date. History is read in insertion order even if the system clock
changes. Other field edits update the revision/timestamp but are not a complete
field-by-field audit trail. There is no public history-edit command.

Dates must be real calendar dates in strict `YYYY-MM-DD` format. Dates use the local
calendar; history uses UTC. Missing application dates/deadlines remain SQL NULL/JSON
null and display as not recorded. Changing status does not invent an application date.
An actual application date cannot be in the future; use next action/deadline for plans.
Past deadlines and applications made after a stated deadline are allowed for historical
or late applications, with notes in the review/detail view. Deadline dates are not
automatically adjusted and do not trigger submissions, rejection or status changes.

Updates change only supplied fields. To clear an optional value, pass an empty string:

```sh
python main.py application-update 1 --deadline "" --application-date "" --notes ""
```

Company/role cannot be cleared. Dates are not inferred from other fields. Notes and
next actions can contain newlines/tabs. Command-line values can remain in your shell
history/process listing: avoid secrets and unnecessary sensitive data in these fields.

### Filtering and pagination

```sh
python main.py application-list --status saved --company Example --role Apprentice
python main.py application-list --deadline-after 2020-01-01 --deadline-before 2099-12-31
python main.py application-list --overdue
python main.py application-list --limit 50 --offset 50
```

Company/role filters are literal substrings (`%` and `_` are not wildcards), combined
with other filters using AND. SQLite's built-in case-insensitivity is primarily ASCII;
international text case folding is not comprehensive. Deadline bounds are inclusive;
unknown deadlines do not match a date range. `--overdue` means **saved** records whose
application deadline is before today; already applied/interviewing records are not
labelled overdue by this filter. It is not an interview/follow-up reminder system.
Lists are newest-ID-first, default to 100 records and print their limit/offset. Use
pagination to see further results. The list API accepts at most 10,001 rows per page.

### Approved CV versions and stored comparisons

The earlier CV import is already a separately approved record/version. Linking records
stores its live ID, original ID, approval timestamp and reviewed-text SHA-256 digest;
it does not duplicate CV text. Comparisons from earlier phases existed in memory or
as human-readable reports. Those existing private reports are **not** automatically
read/imported. To make a comparison available for application links, explicitly store
metadata when generating a new comparison:

```sh
python main.py job-compare 1 --job-file /path/to/job.txt --store
python main.py comparison-list
python main.py comparison-show 1
python main.py application-create --company "Example Ltd" --role "AI Apprentice" --cv 1
python main.py application-create --company "Example Ltd" --role "AI Apprentice" --comparison 1
python main.py application-update 1 --comparison 1
python main.py comparison-delete 1
```

`--store` asks for separate confirmation after showing the comparison. It saves only
CV approval provenance/digest, job-text digest, rule version, outcome counts, creation
timestamp and AI-request/item-count metadata. No document excerpts, filenames, full
report, model response or source file path is added to `job_comparisons`. `ai_attempted`
means assistance was requested, not necessarily sent/successful; item count is not a
count of independently verified matches. A requested file report can still be saved
if metadata storage fails, but the command exits with status 1 to identify that failure.

A comparison link automatically supplies its CV version. Supplying both IDs must
refer to the same approval timestamp/digest; stale or mismatched CV versions are
rejected. Link updates explicitly **replace the link set**: supply both desired IDs,
or select the stored comparison to use its CV. Setting only `--cv` drops the old
comparison link. Preview shows the proposed links before confirmation. To remove
both links and retained provenance snapshots:

```sh
python main.py application-update 1 --clear-links
```

Unrelated field/status updates retain existing links. Deleting a CV or comparison
sets its live foreign key to NULL; the application and original-ID/digest metadata
remain as historical provenance. A comparison with a deleted CV can still identify
that historical approved version, without restoring or reading deleted text. Reused
CV numeric IDs are not silently rebound: the approval timestamp/digest must match.
Hashes/IDs are identifiers, not anonymisation or encryption. Clear links when those
historical identifiers are no longer needed. Deleting a comparison does not delete
CVs, applications, history or report files.

### Transactional migration and safe writes

Phase 3A introduced schema version **2**; Phase 3B introduced **3**, Phase 4A **4**, and Phase 5A **5**. On first database-backed command, the application
checks the application ID, supported version and required columns. It upgrades a valid
version 1 database by adding `applications`, `application_status_history` and
`job_comparisons`, with indexes and foreign keys. Original `profiles`, `cvs` and
`cv_segments` rows/IDs/text are retained. Fresh databases get all tables at the current version.
Repeated startup is idempotent. Future/unknown versions, incomplete schemas, conflicting
table names, unrelated files and inconsistent references are rejected rather than reset.

Initialization, the version marker and migration DDL run in one `BEGIN IMMEDIATE`
transaction. Errors or interruption roll back the whole upgrade. **Before upgrading
an important database, close other app instances and keep a private filesystem backup**
of its SQLite file; existing backup files are never replaced by the migration. No
automatic backup copies of personal data are created. Do not try to open a migrated
database using older application code that does not understand its schema version.

Application creation plus its initial history event, status updates plus history,
and deletion plus history removal are transactionally committed together. Writes lock
before reading; review-based updates/deletes also check a revision to reject stale
reviews rather than overwrite another process's edits. Link snapshots are rechecked
before saving. SQLite waits up to five seconds for locks and reports failure without
an automatic retry or incomplete commit. All user SQL values are bound parameters;
column/table choices come from fixed allowlists. This is a local SQLite application,
not a multi-user server or a tamper-proof audit system.

Application deletion requires confirmation and removes only that application and
its status history. Linked CVs, comparison metadata and exported reports are retained.
There is no bulk-delete command or automatic cascade from a CV to applications.

### Private local JSON export

```sh
python main.py application-export --output local_data/applications.json
python main.py application-export --status applied --include-history --output local_data/applied.json
python main.py application-export --include-notes --include-history --output local_data/detailed.json
```

Exports use a consistent read transaction and include all matching records, independently
of list pagination, up to 10,000 applications. Larger exports fail clearly: narrow
filters and export multiple files. The JSON format has its own `format_version: 1`.
Default fields include application details, entered URLs/next actions, dates/status,
timestamps, revisions and CV/comparison IDs. Notes and history are omitted unless
explicitly requested. CV text, source excerpts, profile names, CV titles, comparison
reports and content digests are never automatically included; the exporter does not
query CV/comparison tables. Content that you manually paste into notes/next actions
can of course be included as application data.

Export asks for confirmation, uses owner-only atomic publication and never overwrites
an existing file or symbolic link. JSON avoids spreadsheet formula execution associated
with CSV workflows. Keep exports under ignored `local_data/`; entered details and URLs
can still be private. SQLite and exports are plaintext; no encryption, accounts,
automatic retention, backups or synchronization have been added. Deleting a database
record does not remove separately exported files or filesystem backups.

### Reproducible synthetic demonstration

From the repository root:

```sh
python -m examples.application_tracking_demo
```

The demo creates a temporary **synthetic version 1** database, migrates it to the current schema, stores
comparison metadata, links an application to its approved CV, records
saved → applied → interviewing across CLI process restarts, filters/exports the record,
then deletes the application/history. It verifies original CV/profile rows and comparison
metadata remain, and that default exports contain no CV text or private notes. All
demo database/export files are removed when it finishes. It never opens the default
database, existing reports or personal CVs and makes no network/paid API calls.

## Local visual dashboard (Phase 3B)

The Streamlit interface manages application tracking while reusing the same
`applications.py` validation, transactional writes, revision checks and status history
as the CLI. CV analysis/import and job comparisons remain available through the CLI.
There is no cloud deployment, login system, automated submission or scraper.
Application tracking makes no AI calls; Interview Practice offers a separate opt-in coaching request. Streamlit is optional for CLI-only use.

### Launch and database selection

From your activated environment in the repository root:

```sh
python -m pip install -r requirements-dashboard.txt
python -m job_assistant.dashboard_launcher
```

The launcher starts Streamlit at `http://127.0.0.1:8501`, sets the project working
directory, explicitly binds localhost and disables usage telemetry. These CLI flags
take precedence over environment/configuration address settings. CORS and XSRF
protection stay enabled. Ctrl+C stops the foreground server. Use a different local
port or an explicitly selected database when needed:

```sh
python -m job_assistant.dashboard_launcher --database /absolute/path/to/demo.sqlite3 --port 8502
```

Without `--database`, the launcher uses `AI_JOB_ASSISTANT_DATABASE` if set, otherwise
the existing `local_data/assistant.sqlite3` beside the project. Relative custom paths
are resolved before launch. The CLI's global `--database` option is unchanged; use
the same path if you want both interfaces to manage the same records:

```sh
python main.py --database /absolute/path/to/demo.sqlite3 application-list
```

The underlying Streamlit entry point is `dashboard.py`. For a direct launch from
the repository root, specify the local binding and telemetry preference explicitly:

```sh
python -m streamlit run dashboard.py --server.address=127.0.0.1 --browser.gatherUsageStats=false
```

The checked-in `.streamlit/config.toml` defines the Midnight Navy theme and safe project
defaults. The launcher is recommended because it applies localhost settings even
when started from another directory. Do not expose the server through a public
address, tunnel or hosting service: there is deliberately no authentication system.
Local binding is not encryption or protection against other users of your device.
`.streamlit/secrets.toml` is ignored by Git; no Streamlit secrets are required or read
by this application. Tests and smoke checks use temporary synthetic databases only.

### Career dashboard appearance and Safari preview

The dashboard opens with a rounded purple-gradient hero, “Your career, moving forward.”,
with actions that open the existing application form and interview practice page.
Five saved-record statistics wrap into a compact responsive grid. The workspace
keeps a compact indigo sidebar with route icons and clear section panels.
Applications offers card and table tabs;
Add Application separates the main form from a summary rail. Interview Practice
places the question beside the response editor and shows STAR feedback in cards.
Skills Roadmap groups career-goal and study-budget controls in two columns, then
shows real saved or previewed weekly milestones as responsive cards. Comparison
context and roadmap title settings remain available in labelled expanders. Cards
show existing values only; there are no salary estimates or invented outcomes.

All workspace pages share a reference-matched deep indigo background (#070619) with a deep indigo sidebar (#100D2C), a subtle header gradient, violet accents,
rounded cards and responsive layouts. Form controls have persistent lavender
borders, readable placeholders and brighter focus indicators. Disabled fields
retain readable text. Native tables retain their scrolling and toolbar controls.

From this project directory, run:

```sh
.venv/bin/python -m streamlit run dashboard.py
```

Keep the terminal running and open `http://127.0.0.1:8501` in Safari. If Streamlit
reports a different port, use its printed local URL. Reload an existing tab after
restarting the server to pick up the theme. Stop the server with Control-C.
This preview uses your existing database; use `AI_JOB_ASSISTANT_DATABASE` with a
separate demo database if you want to experiment with saves.

For repeatable offline browser checks, use an environment with Playwright and
its Chromium browser already installed:

```sh
python tests/browser_dashboard_check.py --artifacts /tmp/job-dashboard-qa
```

The check starts the project’s `.venv` Streamlit server on an available localhost
port, seeds a temporary synthetic database, blocks external browser requests,
and checks all four pages at 390, 768 and 1440 pixels. It verifies field borders,
focus states, disabled controls, offline feedback, progress, table toolbar access,
absence of page-wide overflow and unchanged saved records. Screenshots and the
server log go only to the requested artifacts directory. It makes no AI calls.
Chromium automation does not replace a manual check in Safari.

### Overview, table and details

The overview cards count **all** application records, independent of current filters:

| Card | Definition |
| --- | --- |
| Total applications | All six statuses |
| Saved jobs | `saved` |
| Active applications | `applied` + `interviewing` + `offered` |
| Interviews | `interviewing` (a subset of active) |
| Offers | `offered` (a subset of active) |

The table includes company, role, status, application deadline, deadline state, next
action, follow-up date and action state. Search is a literal, Unicode-casefolded search
across company/role/next action; filter by multiple statuses and follow-up timing.
Native table sorting/scrolling and 25/50/100-row pages keep the view manageable.
Use **Open application** to view/edit a selected row. Empty databases and zero-result
filters have helpful empty states. Overview totals remain exact; table/search data
is limited to the newest 10,000 rows, with an explicit warning if older records exist.
Use the CLI for older records. Records are not cached across user sessions.

Application details include status history, private application notes in the edit
form and link metadata. Linked CV IDs, approval timestamps/digests and comparison
outcome counts are shown where available. CV passages, original extraction, profile
names and full comparison reports are not displayed in the dashboard. Interview Practice
reads a linked approved CV only for local corroboration when you explicitly select it. Link selectors
show only IDs and approval dates; selecting a link for saving invokes the existing
approved-version validation. Job URLs are stored/displayed as text and never fetched.
Application notes are shown only when opening the corresponding record, not in the
overview table. Information intentionally displayed in your browser remains private
application data; keep access to your device and backups controlled.

### Forms, drafts and deletion

Choose **Add application** for company/role, status, optional dates/URL, next action,
follow-up date and notes. Dates start blank; status changes never fabricate an
application date. Native date controls and the shared Python validation provide clear
errors. Required labels, help text, native controls, responsive columns and textual
timing indicators avoid relying on colour alone. The layout uses a restrained light
theme with teal actions and bordered overview cards. Keyboard/screen-reader testing
on target devices is still recommended; no accessibility certification is claimed.

Edit a record and press **Save changes** to commit. Link changes explicitly choose
Keep, Replace or Clear, using the same semantics as the CLI. A browser edit retains
the revision it loaded. If a CLI/other browser changes the record, stale saves and
deletions are rejected, keeping the newer record. **Reload record** explicitly discards
the displayed draft and loads current data. **Refresh list** rereads list/card data;
it does not silently replace an open draft. Unsubmitted form edits are not durable:
switching pages, refreshing the browser, changing application or disconnecting can
discard them. Save before navigating away. After successful creation the form resets,
so a rerun does not duplicate the application.

Deletion has a separate **Review deletion** step, an acknowledgement checkbox and
**Confirm deletion**. It removes only the application/status history; CVs, comparisons
and existing reports remain. The delete action also checks the reviewed revision.
Expected database/permission/lock errors use generic messages without echoing private
exception details. All writes run through the existing transaction-safe services.

### Follow-up dates and completed actions

Schema version **3** adds `follow_up_date`, `action_completed` and
`action_completed_at` to applications. Migration from version 2 is additive and
transactional; original application columns, CV records, revision values, links and
status history are preserved. Version 1 upgrades through version 2 in the same
transaction. Existing rows get no follow-up date, completion=false and no completion
timestamp; no past action completion is inferred. Back up an important database with
other app instances closed before upgrading. Older version 2 code cannot open the
new version 3 schema.

An application deadline and a follow-up date have different meanings:

- **Deadline state** is actionable for saved jobs only: overdue, due today, upcoming
  within seven days, later or no deadline. Applied/interviewing/offered records show
  Submitted; rejected/withdrawn records show Closed. A past application deadline does
  not make a submitted application an overdue task.
- **Action state** uses the next action and follow-up date: overdue, due today,
  upcoming within seven days, later, unscheduled or no action. Completed actions show
  Completed even with past due dates. Rejected/withdrawn records show Closed unless
  already explicitly completed. Offered records may still have actionable follow-ups.

Add a next-action description before assigning a follow-up date or completing it.
Past follow-up dates are allowed. In the detail view, **Mark action complete** records
a UTC completion timestamp; **Reopen action** clears it. Editing the next action in
the edit form reopens it automatically; the existing follow-up date is retained until
you deliberately change/clear it. Editing notes/status alone preserves completion.
There is one current next action per application, not a separate multi-task/history
system. Completion does not change application status or create a status-history
event. No reminders, notifications or background scheduling are implemented.

The CLI supports the same new fields and validation:

```sh
python main.py application-update 1 --next-action "Follow up with recruiter" --follow-up-date 2099-12-01
python main.py application-update 1 --complete-action
python main.py application-update 1 --reopen-action
python main.py application-update 1 --follow-up-date ""
```

Changing next-action text in the CLI also reopens it unless completion is explicitly
supplied in the same command. If clearing the action entirely, clear its follow-up
date as well. Local application JSON exports now include follow-up/completion fields
and a boolean completion value, but continue to exclude CV contents and notes by
default. Export and comparison functionality remain in the CLI in this stage.

### Verification and limitations

The test suite uses [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)
with synthetic records and temporary database paths. Tests cover zero states, cards,
search/filters, creation, validation, edits/history, follow-ups, completion/reopening,
link preservation/clearing, stale writes/deletions, delete confirmation and safe errors.
Migration tests verify version 2 records/history survive version 3 and a failed upgrade
rolls back. A synthetic localhost server health check is smoke-tested separately and then
stopped; it does not verify browser rendering. Tests do not access the real default database or call AI providers. This
change was validated with Streamlit 1.67.0 and Python 3.14.5.

The dashboard is for local single-user tracking, with explicit refresh rather than
real-time collaboration. No public hosting/authentication or automatic application
actions are supported. Native Streamlit columns/table adapt to the viewport, but
manual desktop/mobile visual and screen-reader verification was unavailable in the
development session. Automated interaction tests do not replace those checks.

## Offline interview practice and career coaching foundations (Phase 4A)

The Phase 4A CLI practice workflow is fully offline. It does not read API keys,
use existing OpenAI adapters, make model calls, change the dashboard or infer hiring
probability. No additional dependencies are required. It works without a CV link.

### Start a session and record practice

```sh
python main.py interview-roles
python main.py interview-start --role ai-engineering-apprentice
python main.py interview-list
python main.py interview-show 1
python main.py interview-answer 1 --question 1
python main.py interview-answer 1 --question 1 --star
python main.py interview-answer-show 1
python main.py interview-feedback 1
```

Replace sample IDs with those printed by your commands. Session and answer IDs are
separate: `interview-answer SESSION_ID --question NUMBER` records an answer;
`interview-feedback ANSWER_ID` reviews one saved attempt. `interview-show SESSION_ID`
lists the question prompts, guidance and saved attempt IDs without dumping all answer
text. `interview-list` defaults to 100 sessions; use `--limit`/`--offset` to paginate.

The curated role bank currently provides six questions each for:

| Role ID | Focus |
| --- | --- |
| `ai-engineering-apprentice` | A real project, evaluation/data leakage, privacy/reliability, apprenticeship motivation, teamwork and learning goals |
| `junior-software-engineer` | Debugging, API reliability, design trade-offs, motivation, teamwork and learning goals |
| `data-analyst` | Analysis/data quality, explaining uncertainty, motivation, teamwork and learning goals |
| `general` | Early-career challenges, motivation, explanation, teamwork and reflection |

Use `--count 1` through `--count 6` to select the first N questions deterministically,
and `--title "My practice"` for an optional session title (1–120 characters). These
are original generic practice prompts, not a particular employer's interview bank or
an official apprenticeship assessment. Work, study, volunteering and personal projects
can all provide truthful examples; do not invent experience to fit a prompt.

Starting a session shows the questions and asks for confirmation before saving.
The session snapshots its question text, type, guidance, topics and bank version.
Later question-bank edits do not silently replace an existing session's prompts.
Each new answer is a separate attempt; earlier attempts are never overwritten.

For normal entry, type multiple lines, including blank lines, and finish with `/done`
on its own line. `--star` prompts separately for Situation, Task, Action and Result;
finish each section with `/done`. Use `--answer "..."` only when you are comfortable
with that text remaining in shell history/process arguments; interactive entry is
preferable for personal answers. The normalised answer (outer whitespace removed)
and its feedback are displayed before the save confirmation. Cancel, Ctrl+C or
end-of-input before confirmation does not save a draft or consume an attempt.

Limits are 8,000 characters, 100 lines, 2,000 characters per line and 50 recorded
attempts per question per session. Blank answers, label-only STAR templates, invalid
Unicode and unsupported control characters are rejected without truncation. Start
a new session after the attempt limit. Deleting an attempt does not reset/reuse its
number; new attempts and record IDs stay distinct. An interrupted/failed write does
not consume an attempt number.

### STAR, clarity and coaching feedback

Feedback has separate sections for STAR cues, clarity cues, CV-supported wording,
answer-only claims, uncertain claims, missing detail and conditional suggestions.
It also offers two small role-specific career-practice next steps, such as practising
an explanation or planning a learning artifact. These are suggestions, not assertions
about your skills, achievements or eligibility.

- **Situation:** the real context and relevant constraint.
- **Task:** your specific responsibility or goal.
- **Action:** what you personally did, why and how you checked it.
- **Result:** the actual outcome or learning. Genuine qualitative results are valid;
  numbers must come from your evidence, not a template.

STAR is required only as a practice structure for behavioural questions. Technical,
motivation and reflection questions mark STAR as not required and instead recommend
a direct answer, reasoning/example and limitations where useful. Topic-mention cues
are not correctness or knowledge checks; repeating `training/test/leakage` does not
establish understanding.

For behavioural answers, `explicit_detail` means a recognised label and at least five
words with three distinct words, **not** a verified or high-quality answer. Empty/short
sections are `missing_detail`; unlabelled lexical cues are only `possible_detail`;
repeated headings are ambiguous. Labels are recognised on separate lines, including
common bullets, case variations and S/T/A/R abbreviations. Inline or unusual layouts
can be missed. Use `--star` when you want unambiguous section boundaries.

Readability checks report word count, sentences over 35 words, a small list of vague
phrases and repeated wording. Brief answers may receive a conditional suggestion to
add an example. These are transparent English-language heuristics, not validated
quality measures, personality/communication-ability judgements or a numerical score.
Team wording prompts clarification of your contribution without claiming team outcomes
were solely your own. Suggestions never fill in a fictional result, employer, duration,
qualification or improvement percentage.

### Optional approved-CV evidence

No CV is read by default. To deliberately use one approved local CV version:

```sh
python main.py interview-start --role ai-engineering-apprentice --cv 1
```

This records its ID, approval timestamp and reviewed-text digest, not its contents.
Only that explicitly linked approved CV is consulted when assessing an answer; other
profiles/documents and original uncorrected extraction are not used to fill gaps.

Outcome/activity wording is separated into:

| Feedback category | Meaning |
| --- | --- |
| CV-supported wording | A sufficiently specific, exact case-insensitive phrase occurs in a suitable approved CV passage; not independent verification or proof of individual ownership |
| Answer-only claim | Self-reported wording with no exact available corroboration; not evidence that the claim is false |
| Uncertain/tentative claim | Negative, hypothetical, conflicting, vague or overly long wording cannot establish an achieved outcome |

Evidence includes answer-character offsets and, when corroborated, the CV unit/page/
paragraph reference, reviewed-text offsets and correction marker. Offsets are zero-based
with an exclusive end. A shared `Python` keyword is not proof of an outcome, and `10`
must not be accepted as the numeric prefix of `100` or `10.5`. Different metrics are
never substituted into the candidate's answer. Related negative/tentative CV wording
is conservatively flagged for review. This is still lexical matching, not semantic
fact checking: paraphrases, ownership, context and genuine new experiences can be
missed or misclassified. Only the first 12 detected activity/outcome claims are checked;
300-character excerpt limits and truncation notes keep feedback bounded.

Feedback stores the candidate's answer excerpts and CV **reference metadata**, not
additional CV passages. Any CV wording you deliberately include in an answer remains
part of that answer. If the CV was deleted or no longer matches the approved version,
new feedback runs without replacement-CV corroboration and explains why. Reused numeric
CV IDs are not silently rebound. Recorded feedback remains a snapshot of the evidence
available at recording time; viewing it does not silently regenerate it against a new CV.
If its CV has since been deleted, the viewer warns that the source cannot be rechecked.

Instruction-like lines in answers/CVs are treated as text and excluded from structural/
corroboration checks. Terminal controls are rejected/escaped. No text is executed or
followed as a command or URL. Instruction detection is heuristic; the more fundamental
boundary is that this offline code has no model/tool execution or network step.

### Persistence, review and deletion

Schema **4** adds `interview_sessions`, `interview_questions` and `interview_answers`.
The version 3→4 upgrade adds tables/indexes only, preserving CVs, applications,
follow-ups, comparison records and status history. Older databases upgrade through
their existing migrations within the same transaction. Unknown versions, invalid
schemas and conflicting tables are rejected; migration errors or interruption roll
back the complete upgrade. Back up an important database with other app instances
closed before upgrading; older schema-3-only code cannot open schema 4.

Saving answers atomically records text, answer digest, attempt number, feedback JSON,
feedback-rules version and UTC timestamp. Questions/evidence are rechecked before
committing a reviewed answer; changes since review require another review. Questions
and feedback versions support reproducibility, not tamper-proof or independently
verified records. Existing attempts are immutable through the public API: record a
new attempt to revise an answer. There is no automatic grading, live interviewer,
audio/transcription, dedicated interview export, scheduling or full career plan.

```sh
python main.py interview-answer-delete 1
python main.py interview-delete 1
```

Both deletions require confirmation. Answer deletion removes that answer and feedback
only. Session deletion removes the session, snapshotted questions and all its answer/
feedback attempts, preserving CVs, applications, comparisons and report files. Session
deletion rejects a stale review if another attempt was recorded meanwhile. Deleting
a linked CV does not delete your separately recorded practice answers or their reference
metadata; delete practice records explicitly when no longer needed.

All practice records are local plaintext in the existing private SQLite database.
There is no login, encryption or automatic retention policy. Personal answers and
CV wording you type can be sensitive; avoid unnecessary secrets, protect backups and
remember that intentionally displayed terminal output/redirected files may be retained.
Read/list/show commands do not modify feedback or contact any provider. Parameterised
SQL, transactional writes and predictable errors reuse existing storage foundations.
Phase 4A was CLI-only; Phase 4B adds the Interview Practice workspace described below.

### Synthetic end-to-end demonstration

```sh
python -m examples.interview_practice_demo
```

The demo creates a temporary synthetic schema-3 database with an approved CV and an
application, migrates it, starts an AI Engineering apprenticeship session, records two
answer attempts through separate CLI processes, reviews STAR/evidence feedback and
confirms deletion. It checks that original records/report files are unchanged and
unrelated CV content is not copied into feedback. Temporary files are removed afterward.
It never opens the default database, private CV files or existing reports and makes
no network/paid AI calls. The percentage in this fictional demo is test data, not a
generated achievement for a real candidate.

## Optional OpenAI-assisted CV suggestions (Phase 1C)

This is disabled by default, even if an API key is present. To request it:

```sh
python main.py cv-analyse 1 --openai --model YOUR_MODEL_ID
```

Choose a model available to your account that supports the Responses API and strict
structured outputs. There is deliberately no default model or price assumption.
Check [current OpenAI pricing](https://developers.openai.com/api/docs/pricing) and
your account/project spending limits first. Set `OPENAI_API_KEY` through your local
environment or secret manager; never put a real key in source, a CV or a report.
The app does not load `.env` files automatically or read credentials in offline mode.
No OpenAI SDK installation is needed: the adapter uses standard-library HTTPS.

After showing the offline report, the app explains the transmission and cost limits.
Only typing the exact word **SEND** authorises one external request. `--openai`
alone, `yes`, an empty response or a missing model never sends data. Cancel or press
Enter to retain offline analysis. The reviewed text can include names, contact details
and other private data; it is **not automatically anonymised**. Review/correct it
before import approval if you do not want those details transmitted. The payload
contains reviewed text and unit positions; profile data, original extraction, filenames,
database IDs and unrelated documents are excluded.

| OpenAI limit | Value |
| --- | --- |
| Reviewed input | At most 12,000 characters and 200 units; rejected rather than truncated |
| Encoded request | At most 96,000 bytes, including instructions/schema |
| Output | At most 1,800 tokens; response body at most 65,536 bytes |
| Validated suggestions | At most 12; exact cited quotes of 1–300 characters |
| Transport | One verified HTTPS request to `api.openai.com/v1/responses` |
| Timeout | 30-second socket-operation timeout; not a total wall-clock deadline |
| Retries/tools/redirects | None |

Input/output limits bound usage, **not a guaranteed monetary amount**. Failed requests
or rejected responses may still incur charges. The request sets `store=false`, but
this does not guarantee zero retention: provider abuse-monitoring retention and
account-specific controls may still apply. See [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data).

The model is asked to select from a fixed catalogue of conditional improvement
actions with source-unit IDs and exact quotes. It cannot supply new CV facts or
free-form factual rewrites. Requests use [strict structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
The app also validates response completion, permitted keys/actions, types, item/quote
limits and citations against the approved text. Unknown citations, instruction-bearing
quotes, extra fields, duplicate JSON keys, refusals and incomplete/malformed responses
are rejected. Only locally written conditional advice templates appear in the report,
labelled `OpenAI-selected; review required`. Correct citations do not prove that a
suggestion is relevant, so user review is still necessary. No tools, URLs from the CV,
commands or arbitrary model-generated facts are executed or accepted. These controls
limit consequences of prompt injection; they do not prove the model ignored every
malicious instruction.

Authentication, rate limits, connectivity and validation failures are shown without
printing credentials, response bodies or parser exceptions. The offline report is
retained and can still be exported; successful fallback exits with status 0. No
automatic retry or paid follow-up is made. Optional mode was tested using mocked
responses only, with no live model calls or claims of model-quality validation.

## Document formats and safety limits

| Limit | Default |
| --- | --- |
| Input | Regular PDF, DOCX or UTF-8 TXT file, at most 5 MiB |
| Extraction time | 15 seconds in a separate process |
| PDF pages | 30 |
| Extracted/reviewed text | 200,000 characters each |
| Source units | 2,000 pages, paragraphs or lines total |
| DOCX archive | 500 entries, 20 MiB expanded total, 5 MiB/member, 200:1 expansion |
| DOCX nested tables | At most 10 nesting levels |

Extensions are checked along with format structure/signatures; encrypted PDFs and
Office files, corrupt documents, symbolic links and non-regular files are rejected
with clear errors. Archives are never extracted to disk. DOCX XML entity declarations
are rejected. Extraction warnings/errors from third-party parsers are suppressed;
only safe messages are returned. The child receives bounded file bytes once, not a
path to reopen. Linux also enforces a 512 MiB address-space limit in the extraction
process. macOS/Windows use the timeout and document limits without a hard memory cap;
this is resource containment, not a complete sandbox for hostile files.

PDF units retain page numbers. Scanned/image-only PDFs need OCR, which is not
implemented; partially readable PDFs warn about blank extraction pages. Reading
order and multi-column layouts can be imperfect. DOCX units identify body
paragraphs, nested table rows/cells and defined headers/footers (included once).
DOCX page numbers cannot reliably be inferred without rendering. Text boxes,
images, comments and tracked changes may be omitted, with a review warning.
TXT retains Unicode text and line references (UTF-8 BOM accepted). Other encodings
must be converted locally first. No document scripts, macros or external links
are executed or fetched. Review the extraction against your original document.

Library references: [pypdf text extraction](https://pypdf.readthedocs.io/en/latest/user/extract-text.html)
and [python-docx document iteration](https://python-docx.readthedocs.io/en/latest/api/document.html).

Storage supports **one running writer at a time**. Atomic replacement prevents
partially written reports; it does not merge simultaneous writes. Report history
is read into memory on each save, so this is intended for small local histories.
Avoid choosing a symbolic link as a report destination: replacement replaces the
link itself. Advanced storage belongs to a later phase.

Job-analysis reports contain timestamps, recognised skills, scores and learning
advice. Names, full profiles and original job descriptions are not stored in those
reports. Job matching is local. CV-analysis exports intentionally contain excerpts
and have the separate privacy controls described above. Reports remain plaintext
and should be treated as personal data. The application provides no accounts,
encryption or automatic retention policy. Manage local files with your operating
system. Tests use synthetic descriptions and temporary files only.

`.gitignore` excludes default report files, `local_data/`, virtual environments,
caches and common credential files. Store custom reports under `local_data/` to
keep them excluded. Ignore rules do not remove already tracked or staged files:
the generated report backup was excluded from the proposed release index and kept locally. Review staged content
before any future commit. Existing source/report backups are preserved.

## What scores mean

The initial AI Developer check compares against the original fixed 12-skill
learning catalogue. For each job, the score is:

`matched recognised skills / detected recognised skills × 100`

No recognised skills produces **N/A**, not a misleading 0% or success message.
Aliases, case, repeated whitespace and common hyphenated spellings are normalised.
Unknown skills entered by the user are retained but cannot match requirements
outside the catalogue. Every missing recognised skill has either curated learning
steps or a generic fallback; console and saved results use the same formatting.

**Limitations:** this is keyword detection, not semantic AI. It does not understand
negation (`no Python required` still detects Python), essential versus desirable
criteria, proficiency, experience, qualifications or unrecognised technologies.
For example, Python plus several unknown requirements can yield 100% recognised
coverage. Always read the complete job description; the score is neither overall
suitability nor hiring probability. Context-aware matching is deferred to a later
phase rather than approximated with fragile negation rules.

## Development and tests

Install test dependencies inside your activated virtual environment:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest
```

The development requirements install the extraction libraries plus pytest.
Tests cover normalisation, matching, boundaries, unknown/empty descriptions,
legacy reports, first-run creation, atomic-save failures, CLI validation,
multiline entry, interruptions, import safety and the real `main.py` entry point.
Phase 1B tests generate synthetic PDF, DOCX and TXT documents in temporary
directories, exercise real extraction subprocesses and the CV CLI, and check
database rollback/versioning, SQL injection resistance, review/cancellation,
cascading deletion, corrupt/encrypted files and safety limits. Tests prohibit
network connections in the pytest process and require no online service.
Phase 1C adds synthetic analysis, missing-section/ambiguity/unusual-format cases,
exact citation and correction checks, hostile CV instructions, report save/failure
checks and real offline CLI integration. OpenAI tests use fake HTTPS responses for
consent, privacy/input/output limits, schema/citation validation, refusals, failures
and fallback. They make no paid calls, require no real key and do not benchmark a
live model's output quality.
Phase 2A adds labelled synthetic job/CV evaluation, priority and negation checks,
unknown criteria retention, technology-specific/abbreviation matching, practical
evidence and contradiction handling, exact citations and offline CLI/export tests.
Phase 2B adds mocked AI-job response/schema/citation validation, curated abbreviation
interpretations, conflicting/negative evidence, prompt injection, cost/consent limits,
provider failures, fallback and safe-report tests. All run without a real key or model.
Phase 3A covers real synthetic v1→v2 upgrades and rollback (including interruption),
restart persistence, date/URL validation, all supported status transitions, atomic
history, stale reviews, lock contention, literal filters, safe deletion, approved-CV
version links, comparison metadata, private exports and the reproducible CLI demo.
Phase 3B adds schema 2→3 rollback/preservation, follow-up validation/persistence,
completion timing, overview/filter logic, localhost launcher settings and Streamlit
AppTest interaction tests. Development requirements include the optional dashboard
dependencies; CLI-only users can keep installing just `requirements.txt`.
Phase 4A adds curated question snapshots, STAR/technical-question handling, exact
evidence/metric boundaries, ambiguous/negative wording, prompt injection, persistence,
attempt numbering, stale reviews, version-3→4 rollback/preservation, deletion and an
offline CLI demonstration. All test answers/CVs are synthetic; no live AI is invoked.
They never read or write existing personal reports, CVs or databases. Installation requires
package-index connectivity; once installed the tests run offline.

## Code layout

| File | Responsibility |
| --- | --- |
| `main.py` | Existing entry point; importing does not start the application |
| `job_assistant/catalogue.py` | Original skills, aliases and curated roadmaps |
| `job_assistant/skills.py` | Pure normalisation, detection, matching and analysis |
| `job_assistant/reports.py` | Shared result formatting and atomic text storage |
| `job_assistant/cli.py` | Validated prompts, options and friendly errors |
| `job_assistant/cv_cli.py` | Profile/CV commands and review-before-save workflow |
| `job_assistant/documents.py` | Safe bounded file reading and extraction orchestration |
| `job_assistant/extraction_worker.py` | Local PDF/DOCX/TXT extraction subprocess |
| `job_assistant/storage.py` | Database connections, migration entry point and CV/profile CRUD |
| `job_assistant/migrations.py` | Transactional schema creation/version 1→2→3→4→5 migrations |
| `job_assistant/cv_analysis.py` | Structured offline CV findings, evidence and conditional advice |
| `job_assistant/cv_analysis_report.py` | Terminal formatting and non-overwriting private export |
| `job_assistant/analysis_cli.py` | Analysis command, consent, review and save flow |
| `job_assistant/openai_analysis.py` | Shared bounded HTTPS transport plus CV-suggestion validation |
| `job_assistant/job_requirements.py` | Bounded job entry/import, priority rules and source evidence |
| `job_assistant/job_matching.py` | Conservative offline matching against approved CV text |
| `job_assistant/job_report.py` | Cited comparison report with separate outcome groups |
| `job_assistant/job_cli.py` | Offline comparison command and confirmed export |
| `job_assistant/openai_job_matching.py` | Opt-in AI request, cost estimate and structured response handling |
| `job_assistant/ai_job_validation.py` | Mandatory local validation of cited AI interpretations |
| `job_assistant/applications.py` | Application validation, transactions, filters and status history |
| `job_assistant/comparison_records.py` | Private comparison provenance/counts without source excerpts |
| `job_assistant/application_cli.py` | Application/comparison commands, review and safe errors |
| `job_assistant/application_export.py` | Snapshot-consistent JSON exports without CV source queries |
| `examples/application_tracking_demo.py` | Temporary synthetic migration/tracking demonstration |
| `dashboard.py` | Streamlit entry point |
| `job_assistant/dashboard_launcher.py` | Explicit localhost/telemetry-safe launch and database selection |
| `job_assistant/dashboard_ui.py` | Native forms, tables, metadata details and confirmed deletion |
| `job_assistant/dashboard_logic.py` | Cards, text search, timing labels and table projections |
| `job_assistant/interview_questions.py` | Curated role questions, STAR guidance and practice suggestions |
| `job_assistant/interview_feedback.py` | Deterministic structure/clarity/evidence feedback without scoring |
| `job_assistant/interview_store.py` | Transactional sessions, snapshotted questions and answer attempts |
| `job_assistant/interview_cli.py` | Offline practice, review, confirmation and deletion commands |
| `examples/interview_practice_demo.py` | Temporary synthetic interview/migration demonstration |
| `tests/` | Synthetic pytest unit and integration tests |

Semantic/embedding matching, OCR, automated scraping/submissions,
reminders and live audio/video interviews remain outside the current scope. The original skills-entry
workflow remains available alongside the new approved-CV comparison command.


## Optional AI interview coaching and dashboard (Phase 4B)

Launch the dashboard as above and choose **Interview Practice**. Start a curated
role-specific session (optionally link an approved CV for local wording checks),
choose a question, enter an answer and select **Review offline feedback**. Review
STAR cues, exact answer citations, clarity cues and the existing separation between
CV-supported wording, answer-only claims and uncertain wording. Non-behavioural
questions do not require STAR. CV wording is not independent verification.

You can save the reviewed attempt immediately without an API key or AI request.
For optional AI coaching, enter an explicit compatible OpenAI model ID, read the
question and answer being sent, tick consent and press **Request AI coaching once**.
This sends only that question and answer, plus safe clause offsets. CV text, original
extraction, profile names, filenames, session titles, notes and other records are
excluded. Sensitive information you type into an answer is part of the answer and
will be sent if you consent. API usage may charge your account. Configure
`OPENAI_API_KEY` in the environment; never put it into source control or answers.
Provider retention policies apply: `store=false` requests no stored response but is
not a promise of zero provider retention.

The adapter uses the existing fixed-host HTTPS transport: one bounded Responses
request, 30-second timeout, no tools, redirects or automatic retries, a 96,000-byte
request cap and 65,536-byte response cap. It uses strict structured output and
validates every returned item locally. AI can select only fixed conditional coaching
prompts for STAR, clarity or reasoning, each citing an exact safe answer passage
with character offsets. The request supplies bounded, copyable quote/start pairs
so the model need not count characters or guess punctuation boundaries. Local
validation still checks every quote and offset against the same normalized answer;
it never repairs offsets, searches for substitute evidence or accepts unsafe clauses.
It cannot provide free-form rewritten achievements, scores,
hiring probabilities or alter offline CV evidence states. Invalid output, refusal,
missing credentials, unsupported models, rate limits and connection failures retain
offline feedback. New coaching requests display a fixed, safe error category for
authentication, API billing/quota, rate limits, model availability, connection/timeout,
request rejection, refusal or invalid/incomplete output (including the output token
limit). Coaching structure, citation mismatches, unsafe boundaries and inappropriate
STAR actions have distinct safe notices. Provider messages, response details, API keys and request headers are never
displayed or logged. Credentials must be available in the dashboard process's
environment; a key set in a separate terminal does not update an already running
dashboard. Historical saved notices remain unchanged. Request construction follows the
[official Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

**Save reviewed attempt** records the exact answer, deterministic feedback and
validated coaching snapshot in the existing feedback JSON. Saving never repeats the
AI request. Changing an answer requires another review (and fresh consent for AI).
Question/evidence changes detected at save reject the stale review. Reopening saved
attempts displays historical feedback without regenerating it or contacting OpenAI.
The newest 1,000 sessions are available in the dashboard; CLI pagination covers older
sessions. Individual answers and entire sessions can be deleted with explicit
acknowledgement. Deleting practice leaves CVs, applications and reports intact.

CLI equivalent (interactive answer entry avoids personal text in shell history):

```sh
python main.py interview-answer 1 --question 1 --ai --model YOUR_COMPATIBLE_MODEL_ID
```

`--ai` requires `--model` and a separate interactive confirmation after displaying
the exact question/answer payload. Declining keeps offline review/save available.
Without `--ai`, all existing interview commands remain offline. API keys and consent
are not persisted with attempts. AI coaching is advisory: exact citations cannot
prove prompt relevance, factual truth or technical correctness. Only English offline
heuristics and curated text questions are supported; no audio/video or live interviewer.
No live model call was made during development; synthetic tests mock provider output
and globally block network connections. Live model compatibility remains unverified.

Phase 4B files: `job_assistant/openai_interview.py` (bounded coaching adapter),
`job_assistant/interview_dashboard.py` (review/send/save UI), updates to
`interview_cli.py`, `interview_store.py`, `dashboard_ui.py`, and synthetic tests in
`tests/test_openai_interview.py`, `tests/test_interview_dashboard.py` and
`tests/test_interview_cli.py`.


## Personalised skills roadmaps and learning progress (Phase 5A)

Launch the existing local dashboard and choose **Skills Roadmap**:

```sh
python -m job_assistant.dashboard_launcher
```

Select a target role (AI Engineering apprenticeship, junior software engineering,
data analysis or general early-career learning), enter existing skills separated by
commas and choose **1–20 whole study hours per week**. No CV, API key, account or
external service is needed. Existing skill aliases are normalised using the shared
skills service. You can optionally select a stored CV/job comparison by ID; the
roadmap reads comparison metadata only, never CV text, job files or report files.

Select **Preview skills roadmap** to review the evidence states, transparent rules,
weekly objectives, suggested exercises, mini-projects and estimated effort. Preview
does not save a roadmap. **Save new roadmap** stores the reviewed plan; changing its
inputs or source metadata requires a fresh preview. Existing plans and progress are
never replaced by generating another plan. Suggestions are recommendations, not
verified qualifications, technical assessments or guarantees of employment.

### Evidence states and historical comparisons

- **Confirmed CV wording / supported wording:** a non-ambiguous comparison matched
  positive reviewed wording for that skill. It is not independently verified proficiency.
- **Self-reported:** the user selected a skill, without supporting comparison evidence.
  This does not rewrite an earlier comparison's missing-evidence conclusion.
- **Missing evidence:** the skill is a curated role recommendation or an unmet
  comparison item without positive supporting wording. This does not establish that
  the person lacks the skill.
- **Uncertain:** ambiguous, conflicting, related, qualified, alternative or unclear-priority
  requirements remain uncertain. These receive a clarification task rather than an
  invented diagnosis. Selecting the skill does not resolve that uncertainty.

New `job-compare --store` operations retain a per-requirement snapshot containing
recognised canonical terms, offline status, priority, alternative/qualifier flags and
CV/job character coordinates. No CV/job excerpts, filenames, profile names, AI
interpretations or free-form requirement text are copied into this metadata.
Roadmaps retain comparison/CV identifiers, review timestamp and source digests for
provenance. Completion does not upgrade source evidence or edit a CV/comparison.

Older stored comparisons have counts only. Individual gaps cannot be reconstructed
from counts, so the preview explicitly falls back to curated role recommendations
and self-reported skills. Re-run a comparison and explicitly store a new record if
you want richer evidence; old records are not backfilled or overwritten. Comparisons
are historical snapshots, not automatically revalidated against a changed CV.
Excluded requirements are ignored. Unrecognised criteria remain visible as requirement
numbers needing manual review; the generator does not invent a skill for them.
Specific technologies stay separate in comparison evidence (SQL does not establish
PostgreSQL, for example). Curated role skills are recommendations, not asserted
requirements of every employer.

### Weekly rules, editing and progress

Rules version `1.0` schedules missing-evidence tasks first (4 estimated hours per
skill), then uncertainty clarification (1 hour), then consolidation of self-reported
or CV-supported wording (2 hours). One task occupies each relative week, split into
numbered parts if the effort exceeds the available weekly hours. The estimates are
starting points, not deadlines or promises of mastery; unused weekly time is not
filled automatically. Plans are bounded to 208 weeks. The shared learning catalogue
supplies existing SQL/API/data-analysis steps; other tasks use small local exercises,
synthetic data and mock services. No paid service is required.

Open a saved roadmap to see a text-labelled progress bar and counts of completed and
in-progress milestones. Select a **Weekly milestone** to edit its objective, exercise,
mini-project, recommended evidence and planned hours (within the weekly budget).
Statuses are **not started**, **in progress** and **completed**. Completion requires a
short description of evidence, such as a local artifact path, checks, outcome and a
limitation. Evidence is stored as plain text; paths and URLs are never opened or
fetched. It remains self-reported. Reopening a milestone clears its completion time
and retains its notes. You can rename a roadmap; choose a new plan to change the role
or overall weekly budget while retaining the original progress.

Edits and deletion use a roadmap revision checked inside a write transaction. A
concurrent edit cannot be silently overwritten: the browser preserves the draft and
asks you to **Reload roadmap**. A no-op save does not change the revision. Deletion
requires an acknowledgement and **Confirm roadmap deletion**; only that roadmap and
its milestones are removed. CVs, applications, comparisons, interviews and reports
are retained. Deleting a linked comparison detaches the live link while retaining the
roadmap's historical provenance. The dashboard lists the newest 1,000 roadmaps and
comparison choices; the service supports pagination for older records.

### Persistence and migration

Schema **5** adds `roadmaps`, `roadmap_milestones` and
`comparison_skill_snapshots`, with foreign keys, constraints and indexes. Migration
4→5 adds tables only; it does not alter or rewrite existing tables/records. Versions
1–4 upgrade through the existing steps in one transaction. Errors, conflicting tables
and interruption roll back the complete migration; unknown versions and inconsistent
references are rejected. Reopening a current-version database does not rewrite its
bytes. Keep a private backup with the application closed before upgrading; older
application versions cannot open schema 5.

Roadmaps and completion notes share the existing local plaintext SQLite database and
privacy protections. There is no evidence upload, file inspection, qualification
verification, progress audit trail, automatic rescheduling or external recommendation
fetching. Use non-sensitive descriptions and protect your device and backups.

### Synthetic end-to-end demonstration and tests

```sh
python -m examples.skills_roadmap_demo
python -m pytest -q
```

The demo creates only a temporary synthetic schema-4 database, upgrades it, saves a
synthetic approved CV/comparison and generates an AI apprenticeship roadmap. It edits
and completes a milestone, reopens the database, generates a no-CV plan and confirms
scoped deletion preserves other records and an existing synthetic report. It needs
no API key and makes no network calls. The temporary directory is removed on exit.

Phase 5A tests cover deterministic generation, weekly budgets, evidence uncertainty,
legacy comparisons, invalid input and corrupt metadata, persistent completion,
revision conflicts, no-op edits, scoped/failed deletion, transactional failures,
migration preservation/rollback and Streamlit interactions. All fixtures are synthetic;
the suite blocks network connections. Validation: **711 passed in 7.84s** using
`.venv/bin/python -m pytest -q`.

Implementation modules: `roadmap_rules.py` (pure generation), `roadmap_store.py`
(persistence/progress) and `roadmap_dashboard.py` (Streamlit forms), alongside the
existing skills, catalogue, comparison and migration services. No new dependencies.

## Interface polish and release review (Phase 5B)

This phase changes presentation only: interview STAR cards and separate evidence,
clarity, next-step and limitation sections; a roadmap milestone summary with recorded
completion evidence; clearer page descriptions and small-screen spacing. Existing
SQLite schema, progress, consent and save/delete behaviour are unchanged. **In Progress**
is a display label for the existing `in progress` status; no milestone is reset.

See [RELEASE_READINESS.md](RELEASE_READINESS.md) for the prioritised audit and release
blockers. This working tree is **not yet cleared for public release**. Do not upload
the project folder wholesale: staged/previously tracked files are not protected by
new ignore rules. No release, commit, push or history rewrite was performed.

### Installation and platform scope

The standard-library CLI targets Python 3.10+. The dashboard release-review environment
used **macOS arm64, Python 3.14.5 and Streamlit 1.67.0**. That Streamlit version requires
**Python 3.11+**. Use Python 3.11+ for dashboard installation; older Python/Streamlit
combinations are not certified by this review. Windows and Linux commands are usage
guidance, not evidence of a tested platform matrix. Linux has an extraction-process
memory cap; macOS/Windows rely on time, file, page and archive limits instead. File
permission behaviour also varies by platform. There is no OCR, login, encrypted
SQLite storage or supported public hosting.

Run installation from the project root, inside a virtual environment. Use a maintained,
security-patched pip from the official package registry; the bootstrap pip supplied by
an interpreter can itself have known vulnerabilities (see the release report). Avoid
`sudo pip` and untrusted package indexes. Install `requirements.txt` for document
imports, `requirements-dashboard.txt` for the UI, or `requirements-dev.txt` for the full
synthetic suite. `python -m pip check` checks dependency compatibility; it does **not**
check vulnerabilities. Ranges are not a reproducible lockfile. The public-preparation update now requires
Streamlit >=1.67.0 and Pillow >=13.0.0; an older 1.54.0 trial failed interaction checks
and selected vulnerable Pillow. Security clearance of one installed environment does
not clear every future combination allowed by dependency ranges.

The optional AI adapters use an environment API key; no key is needed for application
tracking, offline interview feedback or roadmaps. A key's presence never authorises a
request. Personal information typed into an explicitly sent answer/CV remains personal
information: there is no automatic anonymisation, guaranteed correctness, guaranteed
employment outcome or guarantee of zero provider retention.

### Synthetic screenshots and manual accessibility checks

Use a **new** temporary directory and an explicit database path, never the default
private database. For example, from the project root this Python snippet creates a
fresh synthetic workspace without reading existing records:

```python
import tempfile
from pathlib import Path
from job_assistant import applications, interview_store, roadmap_store, storage

folder = Path(tempfile.mkdtemp(prefix="aija-screenshots-"))
path = folder / "synthetic.sqlite3"
with storage.database(path) as connection:
    applications.create_application(connection, company="Synthetic Example Ltd",
                                    role="AI Apprentice", next_action="Practise one example")
    session = interview_store.start_session(connection, "general")
    interview_store.record_answer(connection, session, 1,
        "Situation: During a synthetic college project input rows were missing.\n"
        "Task: My task was to check each input row.\n"
        "Action: I tested three local synthetic cases.\n"
        "Result: I learned to report invalid rows clearly.")
    roadmap_store.create_roadmap(connection, "ai-engineering-apprentice", "Python, Git", 3)
print(path)
```

Launch `python -m job_assistant.dashboard_launcher --database /the/printed/path` on a
spare port if another instance is running (`--port 8502`). Keep AI consent unticked.
Capture Applications, the saved interview STAR cards, and a roadmap's weekly summary
and progress form at desktop and approximately 390-pixel phone widths. Only use the
synthetic examples in screenshots. Check every visible field, sidebar, browser tab,
address bar, terminal and notification for private information before sharing. Crop
browser chrome and local paths; do not include real company notes, CV references,
API keys, personal answers or the user's existing In Progress milestone. Screenshots
are optional documentation artifacts, not evidence that accessibility is certified.

Before release, check keyboard-only navigation and visible focus, labelled form fields,
validation recovery without lost drafts, zoom at 200%, collapsed navigation on a narrow
viewport, table scrolling, readable cards and completion notes, and a real screen
reader. Native Streamlit controls and text status labels help, but no WCAG conformance
claim is made. Phase 5B browser automation was unavailable; AppTest cannot establish
pixel layout, contrast, focus order or screen-reader behaviour. No new screenshot or
manual mobile certification was produced in this session.

Phase 5B validation: **718 passed in 8.91s** in the existing environment and
**718 passed in 16.74s** in a freshly installed temporary environment. The focused
Streamlit/presentation interaction run passed **32 tests in 1.94s**. An isolated
localhost startup health check returned HTTP 200 / `ok`, then the synthetic server
was stopped. The dependency-vulnerability audit did find installer-tooling issues;
a green test suite is not a security clearance.


## AI-assisted development and public update status

This project has been developed with AI assistance, including Codex. Automated tests
and the documented manual checks help assess the implementation; AI assistance and a
green test suite are not independent security certification or proof that advice is
correct. Offline matching/feedback/roadmaps use deterministic rules. Optional external
AI assistance is separate, requires explicit consent and can incur API charges; CV/job
modes can send reviewed personal text, while interview coaching sends only its question
and answer. Never treat suggestions as verified qualifications or employment guarantees.

For the proposed public GitHub update, generated reports, local script backups, IDE
metadata, databases, private documents, exports and credentials must remain outside the
release. Ignore rules cannot sanitise an existing commit or prevent all secret formats;
use the reviewed `.public-release-files` allowlist and scan the final staged snapshot.
The generated report and script backups were removed from the index while their local
files were retained; IDE removals are index-only. The final release check stages only
the explicit allowlist, scans that exact snapshot and requires approval before any
commit or push. Nothing is committed or published by running the app or its tests.

The owner has chosen to make the GitHub repository **public without adding a licence**.
No LICENSE, LICENCE or COPYING file is supplied. Public visibility is permitted without
an open-source licence, but it does not grant general permission to use, modify or
redistribute the code. Default copyright rules apply, subject to GitHub's platform
terms allowing users to view and fork public repositories. Third-party dependencies
retain their own licences. See [GitHub's licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).
This is publicly visible source, not a claim of an open-source licence. The remaining
identity/history/snapshot checks are documented in [RELEASE_READINESS.md](RELEASE_READINESS.md).
Publishing source code does not make public hosting of this local, unauthenticated app
safe or supported. Mobile/screen-reader and Windows/Linux support remain uncertified.
