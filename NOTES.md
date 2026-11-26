
# Day 1 - NikshayNavigator Foundation

## 1. Project Setup

- Project: NikshayNavigator
- Python package: `nikshaynavigator`
- Python version: 3.12
- Package manager: uv
- Project structure: src layout
- Dependency management: `pyproject.toml` and `uv.lock`

## 2. Project Definition and Documentation

Created the initial project documentation:

- `README.md` - project overview, target user, problem statement, data sources and target metric.
- `docs/QUESTIONS.md` - 10 evaluation questions, including one unanswerable patient-specific question.
- `docs/REQUIREMENTS.md` - 5 functional and 5 non-functional requirements.

Target user:
Senior Treatment Supervisor in Tiruvallur district who follows approximately 120 TB patients.

Core problem:
Providing reliable TB programme guidance while prioritizing the latest valid NTEP guidelines and avoiding superseded treatment recommendations.

Target metric:
95% latest-guideline correctness across 40 evaluation questions.

## 3. Quality Gates and Secret Management

Configured:

- Ruff for linting and formatting.
- Pytest for automated testing.
- Pre-commit hooks.
- `detect-secrets` for secret scanning.
- `.gitignore` to exclude local and sensitive files.
- `.env.example` for placeholder environment configuration.
- `.env` for private local settings.

Verified that `.env` is excluded from Git.

## 4. FastAPI Service Foundation

Implemented the initial FastAPI application with an application factory.

Main components:

- `config.py` - environment-based configuration using Pydantic Settings.
- `logging_setup.py` - structured JSON logging.
- `store.py` - JSON-based sample record storage.
- `api/deps.py` - dependency injection.
- `api/errors.py` - RFC 9457 problem-details error handling.
- `api/middleware.py` - request ID, request timing and exception handling.
- `api/routes/health.py` - health and readiness endpoints.
- `api/routes/documents.py` - document listing and retrieval routes.
- `api/main.py` - application factory and route registration.

## 5. Initial API Endpoints

Implemented:

- GET `/health` - application liveness.
- GET `/ready` - checks whether sample records are loaded.
- GET `/v1/documents` - document listing with pagination and search.
- GET `/v1/documents/{id}` - retrieve a document by ID.

Additional behaviour:

- HTTP 404 for missing documents.
- HTTP 422 for invalid request parameters.
- RFC 9457 problem-details responses.
- Request IDs included in responses and structured logs.

## 6. Initial Testing

- Created automated API and health tests.
- Initial test suite: 10 passing tests.
- Ruff checks passed.
- Verified application configuration rejects invalid `APP_ENV` values.

## 7. Git and Pull Request

- Development branch: `feat/day-01-foundation`.
- Created and merged PR #1.
- Repository: https://github.com/VARSHINI-24-V/prince28-hlt03-nikshaynavigator/pull/1

---

# Day 2 - Sample Data Completion

## 1. Objective

Complete the initial real-world sample dataset for NikshayNavigator before integrating PostgreSQL.

The Day 1 assignment required at least 5 real records initially, increasing to 20 records by the end of the day.

## 2. Data Source Categories

Collected sample guideline information from public NTEP and Central TB Division sources, including:

- Drug-resistant TB management guidelines.
- TB preventive treatment guidelines.
- Differentiated TB care guidance.
- Technical and operational guidelines.
- NTEP training modules.
- Ni-kshay Poshan Yojana documents.

## 3. Sample Record Structure

The dataset uses fields such as:

- `id`
- `document`
- `year`
- `topic`
- `population`
- `recommendation`
- `supersedes`
- `source_url`

## 4. Data Quality Rules

- Every record must have a unique identifier.
- Use real information from the source documents.
- Do not invent missing values.
- Use `null` when source information is unavailable.
- Preserve document names and publication years.
- Maintain source URLs for traceability.

## 5. Dataset Verification

File: `data/sample_records.json`

- Required target: 20 records.
- Current verified record count: 20.
- Dataset used as the initial source for the Day 3 PostgreSQL migration and loader.

## 6. Day 2 Outcome

The 20-record sample dataset was available as a prerequisite for Day 3 database migration, idempotent loading and PostgreSQL-backed API development.

# Day 3 - PostgreSQL Migration Notes

## 1. Database Setup

- Database: Neon PostgreSQL
- Driver: asyncpg
- ORM: SQLAlchemy (async)
- Migration tool: Alembic

## 2. Database Migrations

### Migration 1

Revision: `fad307f9e292`

Created:
- documents
- pages

### Migration 2

Revision: `98a8d884fea6`

Created:
- `ix_documents_metadata_gin`
- PostgreSQL GIN index using `jsonb_path_ops`

## 3. Idempotent Loader Verification

First run:

```text
records=20 inserted=20 updated=0 unchanged=0
```

Second run:

```text
records=20 inserted=0 updated=0 unchanged=20
```

Modified record run:

```text
records=20 inserted=0 updated=1 unchanged=19
```

Restored record run:

```text
records=20 inserted=0 updated=1 unchanged=19
```

## 4. API Verification

Verified endpoints:

- GET `/health`
- GET `/ready`
- GET `/v1/documents`
- GET `/v1/documents?limit=3`
- GET `/v1/documents?q=tuberculosis`
- GET `/v1/documents?topic=...`
- Invalid metadata filter returns HTTP 400.

## 5. Unit Tests

Original Day 3 tests:

- 16 passed.
- 3 optional integration tests are skipped when `TEST_DATABASE_URL` is not configured.

Additional enhancement tests:

- Database pool monitoring tests.
- API sorting tests.
- Fake repository updated to support sorting.

Full test suite and Ruff checks passed after the repository compatibility update.

## 6. GIN Index EXPLAIN Verification

Query:

```sql
SELECT id, external_id, title
FROM documents
WHERE metadata @> '{"topic": "Drug-resistant TB diagnosis"}'::jsonb;
```

Observed execution plan:

```text
Bitmap Heap Scan on documents
  -> Bitmap Index Scan on ix_documents_metadata_gin

Planning Time: 6.715 ms
Execution Time: 4.283 ms
```

Sequential scans were disabled for this demonstration to show GIN index usage.

## 7. Security

- DATABASE_URL stored in local `.env`.
- `.env` excluded from Git.
- `.env.example` contains placeholder configuration.

## 8. Additional Enhancement: API Sorting

Added sorting support to the documents listing API.

Supported sorting fields:

- `external_id`
- `title`
- `published_on`

Supported sorting directions:

- `asc` – Ascending order.
- `desc` – Descending order.

Example requests:

```text
GET /v1/documents?sort_by=title&order=asc

GET /v1/documents?sort_by=title&order=desc

GET /v1/documents?sort_by=published_on&order=desc
```

Implementation details:

- Sorting is performed at the SQLAlchemy repository layer.
- Allowed sorting fields are controlled through a whitelist.
- Invalid sorting fields return HTTP 400.
- Invalid sorting directions return HTTP 400.
- Sorting parameters are excluded from dynamic metadata filters.
- Existing search, filtering and pagination behaviour is preserved.

Automated tests cover ascending sorting, descending sorting and invalid sorting fields.

## 9. Additional Enhancement: Database Connection Pool Monitoring

Added a database monitoring endpoint:

```text
GET /metrics/db-pool
```

SQLAlchemy connection pool configuration:

- Pool size: 5
- Maximum overflow: 2
- Maximum configured connections: 7
- `pool_pre_ping`: Enabled

Metrics exposed:

| Metric | Description |
|---|---|
| pool_size | Configured pool capacity |
| max_overflow | Maximum additional connections |
| max_connections | Maximum configured connections |
| checked_out | Connections currently in use |
| checked_in | Connections currently idle |
| overflow | Current SQLAlchemy overflow value |
| status | Monitoring endpoint status |

Example response:

```json
{
  "pool_size": 5,
  "max_overflow": 2,
  "max_connections": 7,
  "checked_out": 0,
  "checked_in": 0,
  "overflow": -5,
  "status": "available"
}
```

Note: Pool statistics are live snapshots. A negative overflow value can occur when the pool has not yet created connections.

Database readiness was also verified:

```text
GET /ready
HTTP 200
database: true
```

Automated tests cover:

- Successful pool metrics response.
- Missing database engine returns HTTP 503.

# Day 4 - Docker and Database Testing

## 1. Production Dockerfile

- Created a multi-stage Dockerfile.
- Used Python 3.12 slim base image.
- Used uv for dependency installation.
- Configured a non-root application user.
- Added commit SHA build argument for image version tracking.

## 2. Docker Compose

Configured services:

- FastAPI application
- PostgreSQL with pgvector
- Redis
- Database migration and sample-data loading

Verified service startup and health checks.

## 3. Testing Structure

Organized tests into:

- Unit tests
- Database integration tests

Configured a separate test database for integration testing.

## 4. Test Results

- 28 tests passed.
- 7 database integration tests passed.
- Coverage verification completed.
- Ruff and pre-commit checks passed.

## 5. Developer Commands

Added Makefile and Poe task commands for common development operations.

## 6. GitHub Delivery

- PR #4: Docker and database testing.
- PR #5: Development documentation and environment setup.

PR #4: https://github.com/VARSHINI-24-V/prince28-hlt03-nikshaynavigator/pull/4
PR #5: https://github.com/VARSHINI-24-V/prince28-hlt03-nikshaynavigator/pull/5


# Day 5  - Audit Evidence and Lead Time

### Automatic Deployment Lead Time

Measured from PR merge to successful production smoke test.

| PR | Merge time (IST) | Smoke passed (IST) | Lead time |
|---|---|---|---|
| #7 | 15:14:53 | 15:17:13 | 2m 20s |
| #8 | 15:40:52 | 15:43:19 | 2m 27s |
| #9 | 20:33:21 | 20:36:14 | 2m 54s |

Average lead time: approximately 2m 34s.

### Initial Automatic Deployment - Smoke Test Output

```text
ok   /health -> 200, version 37f70ae633e2eb781ed3044588bcbbdce3e3d7af
ok   /ready -> 200 {'status': 'ready', 'checks': {'database': True}}
ok   /v1/documents?limit=1 -> 200 (total=20, returned=1)
Smoke test passed
```

### Rollback Drill Timing

- Rollback started: 21:01:12 IST
- Rollback smoke test passed: 21:02:00 IST
- Workflow duration: 51 seconds.
- Rollback SHA: `2f5f16a62329384071067016b1ba915efbed4e98`

### Roll-forward Timing

- Roll-forward started: 21:06:32 IST
- Roll-forward smoke test passed: 21:07:17 IST
- Workflow duration: 48 seconds.
- Restored SHA: `e237a9cb0ef26073ba0b0e4bc7c5c8f51f58b59e`

### Database Schema Safety

The rollback changed the application image but did not revert the database schema. No schema-changing migration was introduced between the selected image versions. Both application versions were compatible with the existing schema.

### First Request Performance

UptimeRobot checks `/health` every five minutes. This periodic traffic helps keep the Render service warm and can reduce cold-start delays.

### Remaining Stretch Tasks

- Human deployment approval gate: pending verification/configuration.
- Dependabot weekly updates: pending.
- Pre-commit in CI: pending.
- Lead-time measurement: completed.

### Two Additional Enhancements

- Container vulnerability scanning and SBOM generation: pending.
- Nightly synthetic production monitoring: pending.

### robots.txt

- Site: https://tbcindia.mohfw.gov.in
- Result: HTTP 404 Not Found.
- No robots.txt directives were published at this endpoint.
- RFC 9309 classifies HTTP 4xx as unavailable; resource access is permitted under the robots protocol.
- Website copyright and document-specific reuse restrictions are checked separately.

## D06 · Collecting the corpus

### Start target
- Target: 15 core NTEP guidelines, approximately 1,500 pages.
- First collection: 10 documents.
- Initial download: 10 downloaded, 0 skipped, 0 blocked, 0 failed.

### robots.txt
- Site: https://tbcindia.mohfw.gov.in
- Result: HTTP 404 Not Found.
- No robots.txt directives were published at this endpoint.
- Copyright and document-specific reuse restrictions are checked separately.

### Kill and resume
- Run 1: Pressed Ctrl+C after 4 completed files.
- Run 2: downloaded=6, skipped=4, blocked=0, failed=0.
- Run 3: downloaded=0, skipped=10, blocked=0, failed=0.
- No completed document was downloaded again.

### Initial integrity
- Manifest records: 10.
- Downloaded documents: 10.
- Missing files: 0.
- Partial files: 0.
- Initial corpus size: approximately 135.4 MB.

<!-- D07_PARSER_COMPARISON_START -->
## D07 — Parser comparison

Selection: 10 largest downloaded PDFs by manifest file size.
Both parsers were tested without OCR for a native-text comparison.

| File | Size (MB) | PyMuPDF pages/chars | pypdf pages/chars |
|---|---:|---:|---:|
| 8368587497guidelines-for-pmdt-in-india-1-1be1189b.pdf | 48.24 | 334/857785 | 334/678119 |
| 1874197613standard-treatment-workflows-e143f46c.pdf | 22.69 | FAILED | FAILED |
| 281220200400operational-guidelines-for-tb-services-at-hwc-23-5d396131.pdf | 22.67 | 52/73911 | 52/56152 |
| national-guidance-on-differential-tb-care-final-march-2025-3-29afdcfa.pdf | 18.09 | 105/216182 | 105/170192 |
| 2239437973guidance-documents-on-community-engagement-under-n-050fda29.pdf | 15.75 | FAILED | FAILED |
| guidelines-for-programmatic-management-of-tuberculosis-preve-026160ce.pdf | 12.94 | 123/244632 | 123/219432 |
| 7702334778training-module-on-extrapulmonary-tb-book-24032023-c400daac.pdf | 11.42 | 204/408953 | 204/384613 |
| guidance-document-nutritional-care-support-for-tb-patients-i-e000b6fa.pdf | 10.49 | 107/231595 | 107/189452 |
| national-guidelines-for-management-of-dr-tb-27-3-2025-d1711f6b.pdf | 8.64 | 82/187936 | 82/165143 |
| guidance-document-on-ni-kshay-mitra-initiative-2026-compress-d9a1e68a.pdf | 5.98 | 58/81331 | 58/72047 |

| File | PyMuPDF time (s) | pypdf time (s) | Tables | Verdict |
|---|---:|---:|---:|---|
| 8368587497guidelines-for-pmdt-in-india-1-1be1189b.pdf | 45.12 | 7.57 | 146 | PyMuPDF: more text |
| 1874197613standard-treatment-workflows-e143f46c.pdf | 52.34 | 31.56 | N/A | Manual/OCR required |
| 281220200400operational-guidelines-for-tb-services-at-hwc-23-5d396131.pdf | 13.66 | 0.51 | 13 | PyMuPDF: more text |
| national-guidance-on-differential-tb-care-final-march-2025-3-29afdcfa.pdf | 12.59 | 6.50 | 36 | PyMuPDF: more text |
| 2239437973guidance-documents-on-community-engagement-under-n-050fda29.pdf | 23.86 | 3.95 | N/A | Manual/OCR required |
| guidelines-for-programmatic-management-of-tuberculosis-preve-026160ce.pdf | 6.95 | 1.31 | 27 | PyMuPDF: more text |
| 7702334778training-module-on-extrapulmonary-tb-book-24032023-c400daac.pdf | 11.48 | 3.24 | 41 | PyMuPDF: more text |
| guidance-document-nutritional-care-support-for-tb-patients-i-e000b6fa.pdf | 11.70 | 3.39 | 48 | PyMuPDF: more text |
| national-guidelines-for-management-of-dr-tb-27-3-2025-d1711f6b.pdf | 7.53 | 2.64 | 40 | PyMuPDF: more text |
| guidance-document-on-ni-kshay-mitra-initiative-2026-compress-d9a1e68a.pdf | 19.86 | 5.97 | 23 | PyMuPDF: more text |

### Parser errors

- **data/raw/ctd/1874197613standard-treatment-workflows-e143f46c.pdf — pymupdf:** no_text_layer: Only 0 characters extracted.
- **data/raw/ctd/1874197613standard-treatment-workflows-e143f46c.pdf — pypdf:** no_text_layer: Only 0 characters extracted using pypdf.
- **data/raw/ctd/2239437973guidance-documents-on-community-engagement-under-n-050fda29.pdf — pymupdf:** no_text_layer: Only 0 characters extracted.
- **data/raw/ctd/2239437973guidance-documents-on-community-engagement-under-n-050fda29.pdf — pypdf:** no_text_layer: Only 0 characters extracted using pypdf.

<!-- D07_PARSER_COMPARISON_END -->

## D07 — Parsing Corpus Results

### Corpus processing
- Total manifest documents: 15
- Successfully parsed: 15
- Failed documents remaining: 0
- Total PDF pages: 1,382
- Extracted tables: 508

### OCR recovery
- Initial failures: 2
- Failure reason: no_text_layer
- Recovered using Tesseract OCR: 2
- English language: eng
- OCR parser: pymupdf_ocr
- Native parser: pymupdf

### Parser comparison
- Files compared: 10
- Selection method: largest 10 PDFs by file size
- Parsers: PyMuPDF and pypdf
- Detailed results: see D07 Parser Comparison above

### Limitations
- Corpus contains 1,382 pages against the approximate
  1,500-page start target.
- OCR output requires additional quality validation.
- Heading detection is heuristic and needs citation-level validation.
- Extracted table counts do not guarantee perfect table structure.

### D08 · First real LLM request

- Primary: Gemini
- Fallback: Groq (openai/gpt-oss-20b)
- First question: NTEP initial diagnostic test for presumptive TB
- Provider used: Groq
- First words after: 9.78 seconds
- Total response: 10.26 seconds
- Tokens in: 248
- Tokens out: 253
- Estimated cost: Rs 0.008977
- Attempts: 1 on successful provider
- Fallback: YES

### Answer quality observation

- The model answered using general knowledge, not our NTEP documents.
- Its diagnostic recommendation needs verification against the applicable NTEP algorithm.
- This demonstrates why retrieval and source citations are necessary.

### Tokens: English against Tamil

| Message | tokens in |
|---|---:|
| "Hi" (baseline) | 233 |
| The English sentence | 241 |
| The same sentence in Tamil | 255 |

- English message tokens: 8
- Tamil message tokens: 22
- The Tamil message needs about 2.75 times the tokens of the English one.
- Tamil refund question was declined as outside NikshayNavigator scope.

### What the model does without my documents

- Patient Murugan dose question:
  - Admitted it cannot access individual patient records.
  - Directed user to medication log or healthcare team.

- Off-topic question (2011 Cricket World Cup):
  - Declined in one sentence.
  - Said it was outside NikshayNavigator scope.

- Both requests were answered by Groq fallback.

### Repeated answer consistency experiment

Question:
What diagnostic test does NTEP recommend first for a presumptive TB patient?

Provider: Groq fallback
Model: openai/gpt-oss-20b

Three repeated runs produced inconsistent answers:
- Run 1: Sputum smear microscopy first.
- Run 2: Sputum smear microscopy first.
- Run 3: Xpert MTB/RIF / Ultra first.

All three requests used fallback=YES.

Official-source verification:
- 2026 TB Mukt Bharat Abhiyaan: 100% upfront NAAT for presumptive TB.
- Sputum microscopy is specified for follow-up tests.
- 2025 NTEP DR-TB guidelines also describe upfront molecular testing.

Conclusion:
The model generated contradictory and outdated diagnostic information.
Without retrieval and source citations, its answers must not be treated
as verified NTEP guidance.

### Normal Gemini availability test

- Restored primary model: gemini-3.8-flash
- Gemini returned HTTP 503 due to temporary high demand.
- Gateway successfully fell back to Groq.
- Groq returned HTTP 200.
- Both provider records had the same non-empty request_id.

Latest request metrics:
- First words: 6.67 seconds
- Total time: 7.23 seconds
- Input tokens: 248
- Output tokens: 275
- Estimated cost: Rs 0.009604

Conclusion:
The fallback works even when Gemini is temporarily unavailable.
Request ID correlation is now verified in Postgres.

### Circuit breaker experiment

Primary model deliberately changed to gemini-no-such-model.

- Request 1: Gemini HTTP 404, Groq fallback succeeded.
- Request 2: Gemini HTTP 404, Groq fallback succeeded.
- Request 3: Gemini HTTP 404, circuit breaker opened.
- Request 4: Gemini was skipped; Groq answered successfully.
- After 30-second cooldown: half-open probe called Gemini again.
- Gemini returned HTTP 404; Groq fallback succeeded.
- Circuit breaker reopened after the failed probe.

Restored the original primary model:
gemini-3.8-flash

### Request ID correlation fix

- Removed duplicate ContextVar declaration from gateway.py.
- Captured request ID at the beginning of generate() and stream().
- Passed the captured ID explicitly to the call recorder.
- Added a streaming regression test.
- Verified both Gemini and Groq database records share the same non-empty request_id.

### Final verification

- Unit tests: 106 passed.
- Ruff lint: passed.
- Ruff formatting: 65 files already formatted.
- Dockerfile: prompts copied into builder and runtime stages.

### Gemini alternative model verification

Previous primary model: gemini-3.8-flash
- Returned HTTP 503 due to temporary high demand.

New primary model: gemini-3.5-flash-lite

Direct API ping:
- Gemini: successful pong in 3119 ms.
- Input tokens: 6
- Output tokens: 1.

Gateway integration test:
- Question: What is Nikshay Poshan Yojana?
- Provider: Gemini
- Model: gemini-3.5-flash-lite
- First words: 3.74 seconds
- Total response: 7.27 seconds
- Input tokens: 178
- Output tokens: 78
- Estimated cost: Rs 0.023598
- Attempts: 1
- Fallback: NO

Groq fallback ping:
- Successful pong in 1180 ms.

Conclusion:
Gemini 3.5 Flash-Lite works through the actual NikshayNavigator gateway
as the primary provider. Groq remains available as fallback.

## Extra Feature – AI Answer Feedback & Error Reporting

### Purpose
Added a feedback mechanism so users can report whether NikshayNavigator answers
are helpful and identify problems with generated answers.

### API endpoints

POST /v1/feedback
- Accepts feedback linked to an LLM request_id.
- Supports positive and negative feedback.
- Accepts an optional comment.
- Requires an issue category for negative feedback.
- Rejects duplicate feedback for the same request.
- Accepts feedback only for an existing successful LLM answer.

GET /v1/feedback/summary
- Returns total feedback count.
- Returns helpful and not-helpful counts.
- Returns counts grouped by issue category.

### Feedback categories

- incorrect_information
- outdated_guideline
- missing_citation
- unclear_answer
- other

### Database implementation

New table: answer_feedback

Migration: 51619edb545f

Fields:
- id
- request_id
- helpful
- issue_category
- comment
- created_at

Database constraints:
- Unique feedback per request_id.
- Valid issue category values.
- Positive feedback cannot contain an issue category.
- Negative feedback must contain an issue category.

### Validation and error handling

- Unknown or unsuccessful LLM request: HTTP 404.
- Duplicate feedback: HTTP 409.
- Invalid feedback payload: HTTP 422.
- Comment length limited to 1000 characters.
- Validation error responses exclude submitted input data to avoid
  unnecessarily exposing potentially sensitive information.

### Testing and verification

Feedback API tests:
- 8 passed.

Real PostgreSQL feedback integration tests:
- 4 passed.
- Verified feedback insertion, unknown request rejection,
  duplicate feedback prevention and summary calculation.

Complete integration suite:
- 16 passed.

Complete project test suite:
- 130 passed.

Code quality:
- Ruff lint: passed.
- Ruff formatting: passed.

PostgreSQL integration testing:
- Used an isolated local PostgreSQL Docker container.
- Integration fixture created a temporary database.
- Alembic migrations ran against the temporary database.
- No production database was used for these integration tests.

### Outcome

NikshayNavigator now supports collecting structured user feedback
linked to individual successful LLM responses.

This provides a foundation for identifying incorrect information,
outdated guideline references, missing citations and unclear answers.

# Day 9 – Versioned Prompts, Question Classification and Evaluation

## Corpus verification

Reprocessed all 15 downloaded PDF documents using:

`uv run python scripts/parse_corpus.py --ocr eng`

Neon verification:
- Documents: 15
- Stored page records: 1,382
- Pages with non-empty extracted text: 1,339
- Pages with empty extracted text: 43
- Text extraction coverage: 96.9%

OCR improved the non-empty page count from 1,332 to 1,339.

The remaining 43 empty-text pages have not yet been individually inspected. They may include blank pages, image-only content or pages where extraction remains unsuccessful. They are recorded as an outstanding corpus-quality investigation, not assumed to be blank.

## Versioned classifier prompts

Created four classifier prompt versions:

- `prompts/classify_v1.md`: Baseline category definitions.
- `prompts/classify_v2.md`: Detailed category definitions, classification priority, hypothetical-versus-actual patient distinction and untrusted input handling.
- `prompts/classify_v3.md`: V2 with six classification examples.
- `prompts/classify_v4.md`: V3 with explicit mixed-intent disambiguation and additional examples.

The existing `prompts/chat_system_v1.md` was preserved.

## Prompt loading and classifier implementation

Created:
- `src/nikshaynavigator/llm/prompts.py`
- `src/nikshaynavigator/llm/classify.py`

Prompt loader capabilities:
- Discovers prompt versions using their filenames.
- Sorts versions numerically.
- Loads UTF-8 prompt files.
- Rejects invalid prompt identifiers.
- Reports missing or empty prompts.

Classifier capabilities:
- Builds system and user messages.
- Wraps user questions in `<question>` tags.
- Escapes injected question-tag delimiters.
- Calls the existing LLM gateway with purpose `classify`.
- Records the selected prompt version through the gateway.
- Uses temperature 0.0.
- Accepts only `docs`, `personal` or `off_topic`.
- Rejects invalid or ambiguous model responses.
- Calculates accuracy.
- Detects complete evaluation questions embedded in prompts.

The classifier reuses the existing Gemini/Groq gateway, retries and fallback implementation. It does not create separate provider clients.

## Evaluation dataset

Created `eval/prompt_testset.jsonl`.

Dataset size: 20 questions.

Category distribution:
- docs: 9
- personal: 6
- off_topic: 5

The dataset includes project evaluation questions from `docs/QUESTIONS.md`, patient-specific information requests and unrelated general questions.

The dataset was validated as 20 valid JSONL records with the expected fields and labels.

## Prompt benchmark methodology

Created `scripts/compare_prompts.py`.

Benchmark characteristics:
- Runs each classifier prompt against the same evaluation dataset.
- Uses the existing LLM gateway.
- Uses deterministic temperature 0.0.
- Strictly validates model labels.
- Stores completed results in `eval/cache/`.
- Reuses cached results on subsequent runs.
- Supports resuming after provider failures.
- Records expected and predicted labels, provider, model, latency, token usage, fallback status and estimated cost.
- Checks prompts for evaluation-question leakage before running.

The benchmark cache directory is excluded from Git using `.gitignore`.

## Benchmark results

All four prompt versions completed all 20 questions.

| Prompt | Correct | Accuracy | Coverage | Invalid outputs |
|---|---:|---:|---:|---:|
| classify_v1 | 20/20 | 100% | 20/20 | 0 |
| classify_v2 | 20/20 | 100% | 20/20 | 0 |
| classify_v3 | 20/20 | 100% | 20/20 | 0 |
| classify_v4 | 20/20 | 100% | 20/20 | 0 |

Total completed classifications: 80/80 correct.

All four prompts passed the evaluation-question leakage check.

### Recorded performance observations

| Prompt | Average latency | Estimated total cost |
|---|---:|---:|
| classify_v1 | 2,084 ms | Rs. 0.084842 |
| classify_v2 | 792 ms | Rs. 0.103164 |
| classify_v3 | 2,106 ms | Rs. 0.213812 |
| classify_v4 | 3,107 ms | Rs. 0.412022 |

These are recorded benchmark observations, not a controlled provider comparison. The runs used different provider mixes, and some results were reused from cache. Therefore, latency and cost differences cannot be attributed solely to prompt design.

During the V3 run, a provider rate limit temporarily prevented one question from completing. The benchmark did not cache that failed request. A subsequent run completed the missing question successfully.

## V4 rationale and interpretation

V1, V2 and V3 already achieved 100% accuracy on the 20-question test set.

V4 therefore was not introduced as an accuracy improvement.

Its purpose was to make mixed-intent classification rules more explicit:

- Hypothetical patient scenarios asking for official guideline recommendations are `docs`.
- Questions about official register requirements are `docs`.
- Requests to retrieve actual patient records or use private patient data for a treatment decision are `personal`.

V4 also achieved 20/20 on the same evaluation set.

The current results establish a baseline for this dataset. They do not prove 100% accuracy on unseen or real-world questions. A larger, independently reviewed evaluation set is needed.

## Unit testing

Created `tests/unit/test_classify.py`.

Coverage includes:
- Question message construction.
- Question-tag injection escaping.
- Empty question and prompt validation.
- Valid and invalid classification labels.
- Accuracy calculation and invalid inputs.
- Prompt leakage detection.
- Gateway invocation and metadata.
- Invalid gateway response handling.

Classifier unit tests: 25 passed.

## Remaining work

- Build the strict Pydantic document metadata contract.
- Implement metadata extraction prompts.
- Implement extraction, validation and bounded repair.
- Run extraction on five trial documents and manually verify the results.
- Process the corpus and record successes, failures and repair attempts.
- Add metadata extraction tests and integration coverage.
- Inspect the 43 remaining empty-text pages.
- Decide which classifier prompt version to use after evaluating reliability and cost requirements.
- Integrate the classifier into the chat route only after its behaviour is tested.


## Day 9 — Metadata Extraction Results

### Extraction completion
- Parsed documents in Neon: 15
- Documents extracted with `extract_v2`: 15
- Documents pending: 0
- Documents marked as repaired: 7 (verified using SQL)
- Failed documents in the final extraction run: 0
- Extraction status independently verified using Neon SQL.

### Prompt experiment: v1 vs v2
Same initial five documents were processed with both prompt versions.

| Metric | extract_v1 | extract_v2 |
|---|---:|---:|
| Successful documents | 5 | 5 |
| Repaired documents | 3 | 2 |
| Failed documents | 0 | 0 |
| Input tokens | 15,478 | 18,217 |
| Output tokens | 1,516 | 1,572 |
| Estimated cost | Rs. 0.801173 | Rs. 0.892534 |
| Elapsed seconds | 54.8 | 43.0 |

v2 reduced repair attempts and improved the observed title extraction on the test documents. Its cost was approximately 11.4% higher. This five-document experiment is a baseline, not proof of general extraction accuracy.

### Prompt v2 improvements
- Prioritizes publication dates printed inside documents.
- Distinguishes publication years from catalogue titles and cited years.
- Avoids arbitrary truncation of document names.
- Rejects OCR artefacts and malformed topic tags.
- Separates the actual document identity from related resources.
- Requires recommendations to be supported by supplied text.
- Accounts for extraction from an opening-page excerpt rather than the full PDF.

### Corpus execution
- Extraction uses up to the first three pages and a maximum of 6,000 characters per document.
- Rate limit: 12 documents per minute.
- Metadata is validated with the Pydantic DocMeta schema.
- Invalid JSON or schema output is repaired up to three attempts.
- Valid metadata is merged into the existing document metadata without discarding parser fields.
- Extraction prompt version and attempt information are recorded in metadata.

### Resilience observation
The first full-corpus run encountered Neon connection interruptions (Windows WinError 121 and WinError 64). LLM usage recording and a document metadata update encountered connection failures. The process was stopped, database state was verified, and the seven remaining documents were processed successfully in a fresh run.

This demonstrates successful manual resume through prompt-version-based pending selection. Automatic database reconnection and persistence retry hardening remain potential improvements.

### Quality limitations
- Pydantic validation confirms schema compliance, not factual correctness.
- Source-level spot checks were performed for DR-TB 2025, DR-TB 2021 and the PMTPT FAQ.
- The DR-TB 2025 document is titled 2025 in the catalogue, while its cover states November 2024; the extracted publication year is 2024.
- Not every metadata field is expected to be populated when the supplied source excerpt does not support it.
- Remaining empty parsed pages require separate corpus-quality investigation.

### Empty-page audit — follow-up

A structural and rendering audit identified 43 empty-text page records across 8 PDFs.

Classification from the automated visual audit:
- 15 pages are likely blank: no detected images, drawings or rendered ink.
- 3 pages in document 26 contain minimal vector objects but no detectable rendered ink; classification remains uncertain.
- 10 pages in document 27 contain substantial drawing/background content. A representative page was visually inspected and appeared decorative.
- 14 pages in document 32 contain image/vector content, including infographic and cover material.
- 1 page in document 34 contains substantial vector content and appears to be a publication cover.

OCR experiments:
- Document 32, page 28: partial infographic labels recovered at 300 DPI; 450 DPI remained noisy and incomplete.
- Document 32, page 58: publisher details and URLs successfully recovered at 300 DPI.
- Document 34, page 40: no OCR text recovered at 450 DPI despite visible vector content.
- A representative decorative page from document 27 returned no OCR text.

Limitations and decisions:
- The automated audit covered all 43 empty-text records, but visual inspection was performed on representative samples, not every page individually.
- Empty text does not necessarily mean a blank PDF page.
- Higher DPI alone did not reliably recover vector or infographic content.
- OCR experiments were read-only and did not overwrite database page records.
- Existing parsed data was preserved. No bulk OCR retry was performed based solely on visual heuristics.
- Further visual/vector extraction work remains a corpus-quality improvement task.



## Extra Feature – Question Router Integration

### Purpose
Integrated the existing versioned question classifier into the `/v1/chat` endpoint to prevent unsupported or private-data questions from reaching answer generation.

### Routing behaviour
- `docs`: Continue to the existing LLM answer-generation flow.
- `personal`: Return a fixed response explaining that individual patient records and live treatment status cannot be accessed.
- `off_topic`: Return a fixed response explaining NikshayNavigator's scope.
- Invalid classifier output: Fail closed with HTTP 502.
- Classifier unavailable: Return HTTP 503.

### LLM efficiency and observability
- Uses `classify_v4` before answer generation.
- Personal and off-topic requests require only one LLM call.
- Documentation questions use classification followed by answer generation.
- Classification label, prompt version and usage metadata are included in responses.
- Supports both streaming SSE and non-streaming responses.

### Semantic Year Validation

Added source-level validation to metadata extraction:
- Rejects an extracted year when that year does not appear in the supplied document text.
- Sends the validation error back to the LLM for correction.
- Added a regression test verifying rejection and successful retry.

### Prompt Evaluation Improvement

Enhanced `scripts/compare_prompts.py` with a confusion matrix:
- Rows represent actual labels.
- Columns represent predicted labels.
- Includes an INVALID output category.
- Helps identify classification errors by category.

### Verification

- Classification prompt leakage checks: PASS for all four versions.
- Benchmark dataset: 20 questions.
- All four cached benchmark results: 20/20 correct.
- Invalid outputs: 0.
- Confusion matrix verified.
- Chat API tests: 11 passed.
- Full test suite: 205 passed, 19 skipped.
- Ruff lint: passed.
- Ruff formatting: passed.
