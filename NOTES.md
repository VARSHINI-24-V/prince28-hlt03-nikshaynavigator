
# Day 3 - PostgreSQL Migration Notes

## 1. Database Setup

- Database: Neon PostgreSQL
- Driver: asyncpg
- ORM: SQLAlchemy (async)
- Migration tool: Alembic

## 2. Database Migrations

### Migration 1
Revision: fad307f9e292

Created:
- documents
- pages

### Migration 2
Revision: 98a8d884fea6

Created:
- ix_documents_metadata_gin
- PostgreSQL GIN index using jsonb_path_ops

## 3. Idempotent Loader Verification

First run:
records=20 inserted=20 updated=0 unchanged=0

Second run:
records=20 inserted=0 updated=0 unchanged=20

Modified record run:
records=20 inserted=0 updated=1 unchanged=19

Restored record run:
records=20 inserted=0 updated=1 unchanged=19

## 4. API Verification

- GET /health
- GET /ready
- GET /v1/documents
- GET /v1/documents?limit=3
- GET /v1/documents?q=tuberculosis
- GET /v1/documents?topic=...
- Invalid metadata filter returns HTTP 400

## 5. Unit Tests

16 passed.

3 optional integration tests are skipped when TEST_DATABASE_URL is not configured.

## 6. GIN Index EXPLAIN Verification

Query:

SELECT id, external_id, title
FROM documents
WHERE metadata @> '{"topic": "Drug-resistant TB diagnosis"}'::jsonb;

Observed execution plan:

Bitmap Heap Scan on documents
  -> Bitmap Index Scan on ix_documents_metadata_gin

Planning Time: 6.715 ms
Execution Time: 4.283 ms

Sequential scans were disabled for this demonstration to show GIN index usage.

## 7. Security

- DATABASE_URL stored in local .env
- .env excluded from Git
- .env.example contains placeholder configuration
