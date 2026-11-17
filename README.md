# NikshayNavigator 🏥

**An AI-powered NTEP guideline assistant for healthcare field staff.**

NikshayNavigator is a GenAI-based question-answering system designed to help healthcare field staff access accurate information from official National Tuberculosis Elimination Programme (NTEP) guidelines.

It answers questions about TB diagnosis, drug-resistant TB treatment regimens, TB preventive treatment, Ni-kshay Poshan Yojana and reporting procedures, with references to the relevant government guideline documents.

## 🎯 Problem Statement

NTEP guidance is distributed across multiple government documents, including DR-TB guidelines, TB preventive treatment guidelines, differentiated TB care guidance, technical and operational guidelines, and training modules.

Newer documents may replace older recommendations. Healthcare field staff need a reliable way to identify the latest valid guidance without accidentally using superseded treatment recommendations.

NikshayNavigator aims to address this problem through guideline-based question answering with source citations and guideline version tracking.

## 👤 Target User

**Senior Treatment Supervisor in Tiruvallur district**

A healthcare field professional who follows approximately 120 TB patients and answers questions from patients and private doctors.

## ✨ Key Features

- **Guideline-Based Q&A:** Answers TB programme questions using official NTEP and Central TB Division documents.
- **Source Citations:** Provides the guideline document name and publication year for every guideline-based answer.
- **Latest Guideline Prioritization:** Prioritizes the latest valid guidance when older and newer documents disagree.
- **Guideline Timeline:** Identifies the guideline year used and explains whether a newer document changed the recommendation.
- **Safe Information Handling:** Clearly identifies unavailable information and avoids inventing patient-specific details.
- **Version Consistency:** Prevents mixing treatment recommendations from different guideline years.

*These are the intended project capabilities; implementation and evaluation are in progress.*

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

Only official public government documents will be used as guideline sources.

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
| Data Validation | Pydantic |
| API Server | Uvicorn |
| Testing | Pytest |
| Code Quality | Ruff |
| Version Control | Git and GitHub |

## 📊 Target Evaluation Metric

**95%+ latest-guideline correctness**

The target is to achieve at least 95% correctness on a set of 40 evaluation questions where older and newer guideline documents differ.

## 📁 Project Structure

```text
nikshaynavigator/
│
├── docs/
│   ├── QUESTIONS.md
│   └── REQUIREMENTS.md
│
├── src/
│   └── nikshaynavigator/
│       └── __init__.py
│
├── .gitignore
├── .python-version
├── README.md
├── pyproject.toml
└── uv.lock
```

## ⚙️ Local Development Setup

### Prerequisites

- Python 3.12 or later
- Git
- uv

### 1. Clone the repository

```bash
git clone https://github.com/VARSHINI-24-V/prince28-hlt03-nikshaynavigator.git
cd prince28-hlt03-nikshaynavigator
```

### 2. Install dependencies

```bash
uv sync --dev
```

### 3. Activate the virtual environment (Windows PowerShell)

```powershell
.venv\Scripts\Activate.ps1
```

### 4. Verify the environment

```bash
uv run python --version
```

## 🧪 Testing

Run the automated tests using:

```bash
uv run pytest
```

Run code quality checks using:

```bash
uv run ruff check .
```

*Application tests and API execution will be added as implementation progresses.*

## 📌 Project Status

**Current phase:** Initial project foundation and documentation.

Upcoming development activities:

- Guideline document collection and processing.
- Document parsing and metadata extraction.
- Guideline version tracking.
- Retrieval-Augmented Generation (RAG) pipeline.
- Citation-aware answer generation.
- FastAPI endpoint development.
- Evaluation using the 40-question test set.

## 📄 Documentation

- [Evaluation Questions](docs/QUESTIONS.md)
- [Project Requirements](docs/REQUIREMENTS.md)

## ⚖️ Disclaimer

NikshayNavigator is an educational and development project based on public government guidelines. It is intended to support access to programme guidance and is not a substitute for professional clinical judgement or official medical decision-making.

---

**Project:** NikshayNavigator
**Programme:** HLT-03 Healthcare
**Repository:** `prince28-hlt03-nikshaynavigator`
