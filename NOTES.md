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
