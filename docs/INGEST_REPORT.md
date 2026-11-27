# Day 10 – Ingestion Queue and Worker Report

**Date:** 27 November 2026
**Branch:** `feat/day-10-queue`
**Project:** NikshayNavigator

## 1. Objective

Implement asynchronous document ingestion using FastAPI, Redis, ARQ workers and PostgreSQL.

The API accepts ingestion requests and queues background jobs. Workers fetch documents, verify SHA-256 hashes, parse PDFs, perform OCR when necessary, and store document metadata and page content.

## 2. Architecture

- FastAPI: Ingestion submission, job progress and dead-letter endpoints.
- Redis: Background job queue.
- ARQ: Asynchronous worker execution.
- PostgreSQL: Persistent ingestion jobs, items, documents and pages.
- PyMuPDF and Tesseract: PDF parsing and OCR.
- SHA-256: Content verification and duplicate prevention.

### API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/v1/ingest` | Submit ingestion request |
| GET | `/v1/ingest/{job_id}` | Check job progress |
| GET | `/v1/ingest/dead-letter` | Retrieve unresolved failures |

The ingestion endpoint is protected using `X-Admin-Token`.

## 3. Corpus Verification

- Manifest records: 20
- Successfully downloaded: 20
- Verified: 20
- Missing files: 0
- Corrupt files: 0
- Partial files: 0
- Duplicate manifest records: 0

## 4. Ingestion Results

Ten distinct PDFs were successfully ingested.

| Document | Pages |
|---|---:|
| Airborne Infections and TB Guidelines 2026 | 208 |
| Handheld X-ray Device Guidance | 27 |
| Cy-Tb Skin Test SOP | 8 |
| 1HP TPT Guidance | 4 |
| 3RH TPT Guidance | 4 |
| DR-TB Guidelines 2025 | 82 |
| Programmatic DR-TB Guidelines 2021 | 334 |
| PMTPT Guidelines 2021 | 123 |
| PMTPT FAQ 2021 | 11 |
| Differentiated TB Care 2025 | 105 |
| **Total** | **906** |

All ten documents were stored successfully.

## 5. Reliability and Recovery

### Retry behaviour

DR-TB 2025 initially failed because of a Leptonica OCR concurrency error.

The retry succeeded:

- Original item: ID 6, failed.
- Retry item: ID 11, done.
- Successfully stored pages: 82.

### Crash recovery

Two documents were recovered and successfully re-enqueued after earlier worker timeouts:

- DR-TB 2021: 334 pages.
- Differentiated TB Care 2025: 105 pages.

### Idempotency

Both the failed original item and successful retry point to the same document record.

- Document ID: 30.
- Stored pages: 82.
- Duplicate document records: 0.

### Dead-letter handling

The dead-letter query now excludes failed items when a matching successfully ingested PDF exists.

The original failed record remains preserved in PostgreSQL.

After rebuilding the API, the dead-letter endpoint returned:

`{"count": 0, "items": []}`

## 6. Testing

| Validation | Result |
|---|---:|
| Unit tests | 221 passed |
| New PostgreSQL integration test | 1 passed |
| Full test suite | 241 passed |
| Ruff lint | Passed |
| Ruff formatting | Passed |

The regression test verifies successful retry filtering, unresolved failure visibility and preservation of the original failure record.

## 7. Local Deployment

Docker Compose services verified:

- PostgreSQL
- Redis
- FastAPI
- ARQ worker

The API was exposed on port 8001.

Local ingestion, retries, recovery and dead-letter filtering were verified.

## 8. Remaining Delivery Tasks

- Verify Render deployment.
- Verify production API and worker health.
- Complete GitHub pull request.
- Apply the `week-2` tag after final delivery validation.

## 9. Conclusion

Day 10 ingestion implementation and local reliability validation were completed.

Ten official guideline PDFs containing 906 pages were successfully ingested. Retry handling, worker recovery, SHA-256 deduplication, dead-letter filtering and PostgreSQL integration testing were verified.

Remote deployment and GitHub delivery remain pending.

<!-- INGEST_REPORT_GENERATED_START -->

## Database-generated ingestion results

- **Generated at (UTC):** 2026-11-27T17:14:13.905012+00:00
- **Jobs included:** 1
- **Requested items:** 20
- **Done:** 20
- **Skipped:** 0
- **Failed:** 0
- **Queued:** 0
- **Running:** 0
- **Pages recorded by ingestion items:** 1633
- **Extracted text characters:** 3,676,918
- **Estimated tokens (characters / 4):** 919,230
- **Estimated tokens per PDF page:** 562.9
- **Items retried:** 3
- **All selected jobs finished:** Yes

### Database document verification

- Distinct ingested documents (`doc_type != record`): 20
- Distinct external IDs: 20
- Stored page rows in database: 1633
- Duplicate external IDs: 0

### Individual ingestion jobs

| Job ID | Created at | Requested | Done | Skipped | Failed | Queued | Running | Pages | Retries |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| be270da149fc4428938ec7e4040edeac | 2026-11-27T15:26:46.267082+00:00 | 20 | 20 | 0 | 0 | 0 | 0 | 1633 | 3 |

### Retry details

- Item 9: Guidance Tool for TB Notification in India 2012 (attempts: 2)
- Item 10: Frequently Asked Questions on TB Notification in India (attempts: 2)
- Item 15: Standard Treatment Workflows for Drug-Sensitive TB under NTEP (attempts: 2)

### Interpretation

- Ingestion item counts and page totals are read from PostgreSQL.
- Document uniqueness is checked using `external_id`.
- Stored page rows are counted independently from item page totals.
- A job is considered finished when all requested items are in terminal states and none remain queued or running.

<!-- INGEST_REPORT_GENERATED_END -->

## What I learnt

1. I learned that HTTP 202 means the ingestion request is accepted; the worker processes documents asynchronously.
2. I learned that PostgreSQL preserves job status and retry attempts, while Redis manages the work queue.
3. I learned that content-hash idempotency and retry handling allow interrupted jobs to recover without duplicating documents.
