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


# Day 5 - CI/CD, Production Deployment and Rollback

## 10. Continuous Integration

- GitHub Actions CI workflow: `.github/workflows/ci.yml`
- CI runs on pull requests and pushes to main.
- Checks include Ruff linting, tests, coverage and Docker image build.
- Docker images are pushed to GHCR on main.
- PR #6: https://github.com/VARSHINI-24-V/prince28-hlt03-nikshaynavigator/pull/6

## 11. Main Branch Protection

- Main branch protected using GitHub ruleset `protect-main`.
- Pull requests required for changes.
- Required status checks:
  - `lint and test`
  - `build image`
- Branch deletion and force pushes restricted.

## 12. Production Deployment

- Hosting: Render
- Live URL: https://nikshaynavigator.onrender.com
- API documentation: https://nikshaynavigator.onrender.com/docs
- Health endpoint: https://nikshaynavigator.onrender.com/health
- Database: Neon PostgreSQL
- Container registry: GHCR
- CD workflow: `.github/workflows/cd.yml`
- Deployment is triggered automatically after successful CI on main.
- PR #7: https://github.com/VARSHINI-24-V/prince28-hlt03-nikshaynavigator/pull/7

## 13. Smoke Test Verification

Verified production endpoints:

- GET `/health` - HTTP 200
- GET `/ready` - HTTP 200, database true
- GET `/v1/documents?limit=1` - HTTP 200
- Total seeded documents: 20

Initial automatic deployment:
https://github.com/VARSHINI-24-V/prince28-hlt03-nikshaynavigator/actions/runs/44713520380

## 14. Uptime Monitoring

- Monitoring tool: UptimeRobot
- Monitor URL: `https://nikshaynavigator.onrender.com/health`
- Check interval: 5 minutes
- Health endpoint supports GET and HEAD requests.
- Monitor status verified as UP.

## 15. Rollback Drill

### Rollback

- Workflow run: CD #4
- Run URL: https://github.com/VARSHINI-24-V/prince28-hlt03-nikshaynavigator/actions/runs/44764074191
- Rolled back to image SHA:
  `2f5f16a62329384071067016b1ba915efbed4e98`
- Workflow duration: 51 seconds
- Smoke test passed.
- `/health` reported the rollback version.
- `/ready` confirmed database readiness.

### Roll-forward

- Workflow run: CD #5
- Run URL: https://github.com/VARSHINI-24-V/prince28-hlt03-nikshaynavigator/actions/runs/44764982211
- Restored image SHA:
  `e237a9cb0ef26073ba0b0e4bc7c5c8f51f58b59e`
- Workflow duration: 48 seconds
- Smoke test passed.
- `/health` reported the restored version.
- `/ready` returned database true.
- Documents endpoint returned 20 total records.

### Migration Safety

- Manual rollback and roll-forward runs skipped database migrations.
- Production database readiness was verified after both deployments.

## 16. Secrets and Configuration

GitHub Actions secrets:
- `DATABASE_URL`
- `RENDER_DEPLOY_HOOK`

GitHub Actions variable:
- `LIVE_URL`

Sensitive values are stored as secrets and are not committed to the repository.
