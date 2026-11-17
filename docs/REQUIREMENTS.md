
# NikshayNavigator – Project Requirements

## 1. Functional Requirements

### FR-01: Guideline-Based Question Answering
The system shall accept TB programme-related questions from field staff and provide answers based on official NTEP and Central TB Division guidelines.

### FR-02: Source Citation
Every guideline-based answer shall include the source document name and publication year so that users can verify the recommendation.

### FR-03: Latest Guideline Prioritization
When multiple guideline versions contain conflicting recommendations, the system shall prioritize the latest valid guideline and identify superseded guidance.

### FR-04: Guideline Timeline
The system shall display the guideline year used for each answer and indicate whether a newer document has changed the recommendation.

### FR-05: Unavailable Information Handling
The system shall clearly indicate when the requested information is unavailable in its connected sources and shall not fabricate patient-specific information or clinical recommendations.

## 2. Non-Functional Requirements

### NFR-01: Guideline Accuracy
The system shall achieve at least 95% latest-guideline correctness on a test set of 40 questions where older and newer guideline documents differ.

### NFR-02: Source Traceability
100% of guideline-based answers shall provide a traceable document name and publication year.

### NFR-03: Version Consistency
The system shall not combine treatment regimen recommendations from different guideline years in a single answer.

### NFR-04: Reliability
The API shall expose a health endpoint and a readiness endpoint to distinguish service availability from successful loading of guideline records.

### NFR-05: Maintainability
The application shall use a modular Python package structure, automated tests, Ruff code-quality checks and pre-commit hooks.
