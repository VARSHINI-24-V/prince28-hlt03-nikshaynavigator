
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
