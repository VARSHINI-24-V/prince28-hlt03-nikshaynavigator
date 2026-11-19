# NikshayNavigator 🏥

**An AI-powered NTEP guideline assistant for healthcare field staff.**

NikshayNavigator is a GenAI-based question-answering project designed to help healthcare field staff access accurate information from official National Tuberculosis Elimination Programme (NTEP) guidelines.

The project focuses on questions about TB diagnosis, drug-resistant TB treatment regimens, TB preventive treatment, Ni-kshay Poshan Yojana and reporting procedures, with references to relevant government guideline documents.

## 🎯 Problem Statement

NTEP guidance is distributed across multiple government documents, including DR-TB guidelines, TB preventive treatment guidelines, differentiated TB care guidance, technical and operational guidelines, and training modules.

Newer documents may replace older recommendations. Healthcare field staff need a reliable way to identify the latest valid guidance without accidentally using superseded treatment recommendations.

NikshayNavigator is being developed to address this problem through guideline-based question answering, source citations and guideline version tracking.

## 👤 Target User

**Senior Treatment Supervisor in Tiruvallur district**

A healthcare field professional who follows approximately 120 TB patients and answers questions from patients and private doctors.

## ✨ Intended Capabilities

- **Guideline-Based Q&A:** Answer TB programme questions using official NTEP and Central TB Division documents.
- **Source Citations:** Provide the guideline document name and publication year for guideline-based answers.
- **Latest Guideline Prioritization:** Prioritize the latest valid guidance when older and newer documents disagree.
- **Guideline Timeline:** Identify the guideline year used and explain whether a newer document changed the recommendation.
- **Safe Information Handling:** Identify unavailable information and avoid inventing patient-specific details.
- **Version Consistency:** Avoid mixing treatment recommendations from different guideline years.

These are project goals; retrieval-augmented, citation-aware answer generation and the full evaluation target remain under development.

## 📚 Data Sources

Official government sources:

1. [Central TB Division – Guidelines](https://tbcindia.mohfw.gov.in/guidelines/)
2. [Central TB Division – Documents and Downloads](https://tbcindia.mohfw.gov.in/documents-downloads/)

Initial document scope:
- 15 core guidelines.
- Approximately 1,500 pages.

Extended document scope:
- All relevant guidelines, training modules and circulars.
- Approximately 5,000+ pages.

Only official public government documents are intended to be used as guideline sources.

## ⚠️ Key Technical Challenge

**Superseded Guidance and Guideline Version Conflicts**

Drug-resistant TB treatment recommendations have changed between the 2021 and 2025 guidelines.

NikshayNavigator must:
- Identify the latest valid guideline.
- Prefer newer valid recommendations over superseded guidance.
- Explain when an older document disagrees with a newer document.
- Never combine treatment regimens from different guideline years.

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python 3.12+ |
| Project Management | uv |
| Backend Framework | FastAPI |
| Data Validation / Settings | Pydantic |
| API Server | Uvicorn |
| Database | PostgreSQL with pgvector |
| Cache / Service | Redis |
| Database Migrations | Alembic |
| Testing | Pytest |
| Code Quality | Ruff and pre-commit |
| Version Control | Git and GitHub |

## 📊 Target Evaluation Metric

**95%+ latest-guideline correctness**

The target is to achieve at least 95% correctness on a set of 40 evaluation questions where older and newer guideline documents differ. This is a target, not a measured result.

## 📁 Project Structure

```text
.
├── docker/
│   └── initdb/
├── docs/
│   ├── QUESTIONS.md
│   └── REQUIREMENTS.md
├── migrations/
├── scripts/
├── src/
│   └── nikshaynavigator/
│       ├── api/
│       │   └── routes/
│       ├── db/
│       ├── config.py
│       ├── logging_setup.py
│       └── main.py
├── tests/
│   ├── integration/
│   └── unit/
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pyproject.toml
└── uv.lock
```

## ⚙️ Local Development Setup

### Prerequisites

- Python 3.12 or later
- Git
- uv
- Docker Desktop (for the containerized PostgreSQL and Redis services)

### 1. Clone the repository

```bash
git clone https://github.com/VARSHINI-24-V/prince28-hlt03-nikshaynavigator.git
cd prince28-hlt03-nikshaynavigator
```

### 2. Configure environment variables

Copy the example file:

**Windows PowerShell**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux**
```bash
cp .env.example .env
```

Review the values in `.env` and configure any required environment-specific settings. Do not commit `.env` or real credentials.

### 3. Install dependencies

```bash
uv sync --dev
```

You can use `uv run` for project commands without manually activating the virtual environment.

### 4. Start the application stack

Make sure Docker Desktop is running, then execute:

```bash
docker compose up --build -d
```

Compose starts PostgreSQL (pgvector) and Redis, runs the migration and sample-data loading job, and starts the API after its dependencies are ready.

Check service status:

```bash
docker compose ps
```

View API logs:

```bash
docker compose logs -f api
```

### 5. Access the API

The host ports configured in `docker-compose.yml` are:

- API documentation: [http://localhost:8001/docs](http://localhost:8001/docs)
- Liveness: [http://localhost:8001/health](http://localhost:8001/health)
- Readiness: [http://localhost:8001/ready](http://localhost:8001/ready)

PostgreSQL is exposed on host port `5433`; Redis is exposed on host port `6379`.

### 6. Stop the services

```bash
docker compose down
```

To also remove the PostgreSQL data volume (this permanently deletes the local database data):

```bash
docker compose down -v
```

## 🧪 Testing and Code Quality

Run the full test suite:

```bash
uv run pytest -v
```

Run only unit tests:

```bash
uv run pytest tests/unit -v
```

Run integration tests against the dedicated `app_test` database created by the PostgreSQL initialization script. Start the Docker Compose database first.

**Windows PowerShell**
```powershell
$env:TEST_DATABASE_URL = "postgresql://app:app@localhost:5433/app_test"
uv run pytest tests/integration -v
```

**macOS / Linux**
```bash
TEST_DATABASE_URL="postgresql://app:app@localhost:5433/app_test" uv run pytest tests/integration -v
```

Run lint and formatting checks:

```bash
uv run ruff check .
uv run ruff format --check .
```

Run all configured pre-commit hooks:

```bash
uv run pre-commit run --all-files
```

The Day 4 development run completed with **28 tests passing**, including 7 database integration tests. This is a development verification result, not the 40-question clinical/guideline accuracy evaluation.

## 🧰 Useful Development Commands

| Task | Command |
|---|---|
| Run API locally with reload | `uv run poe dev` |
| Run all tests | `uv run pytest -v` |
| Run unit tests | `uv run poe test` |
| Run integration tests | `uv run poe test-integration` |
| Run coverage | `uv run poe cov` |
| Lint | `uv run ruff check .` |
| Check formatting | `uv run ruff format --check .` |
| Apply formatting | `uv run ruff format .` |
| Apply migrations locally | `uv run poe migrate` |
| Load sample records locally | `uv run poe seed` |

For the Docker-based workflow, use `docker compose up --build -d` so the services, migrations and sample-data loading run in the configured order.

## 📌 Project Status

**Current phase:** Backend foundation and containerized database/API infrastructure.

Implemented and verified in the Day 4 development workflow:
- FastAPI application with health and readiness endpoints.
- PostgreSQL and Redis services using Docker Compose.
- Alembic database migrations and sample-record loading.
- Document listing, retrieval and search API routes backed by the database.
- Unit and database integration tests.
- Ruff and pre-commit quality checks.

Next development activities:
- Collect and process the full set of official NTEP guideline documents.
- Improve document parsing and metadata extraction.
- Implement guideline version and supersession tracking.
- Build the retrieval-augmented generation (RAG) pipeline.
- Add citation-aware answer generation and safe handling of unavailable information.
- Evaluate against the 40-question test set and measure latest-guideline correctness.

## 📄 Documentation

- [Evaluation Questions](docs/QUESTIONS.md)
- [Project Requirements](docs/REQUIREMENTS.md)

## ⚖️ Disclaimer

NikshayNavigator is an educational and development project based on public government guidelines. It is intended to support access to programme guidance and is not a substitute for professional clinical judgement or official medical decision-making.

---

**Project:** NikshayNavigator  
**Programme:** HLT-03 Healthcare  
**Repository:** `prince28-hlt03-nikshaynavigator`
