# CMA Compiler History

## 2026-01-25: Developer Productivity Tools

### Added
- **One-Command Runner**: Created `scripts/dev.sh` to handle environment activation and server startup in a single step.
- **Idempotent Setup**: Created `scripts/setup.sh` to automate virtual environment creation and dependency installation.
- **Project Structure**: Organized automation scripts into a dedicated `scripts/` directory.

### Changed
- **Requirements**: Added `weasyprint` to `requirements.txt` to ensure PDF generation works out-of-the-box.
- **Documentation**: Simplified the "Quick Start" section in `README.md` to use the new scripts.

### Verified
- **Scripts**: Manually verified `./scripts/setup.sh` and confirmed `./scripts/dev.sh` starts the FastAPI server correctly.

---
## 2026-01-25: UI Refinement & PDF Integration

### Added
- **Interactive Assumptions**: Added Bed/Bath/Radius inputs to the Review Screen sidebar (`review.html`), wired to `PUT /ui/update-criteria`.
- **Score Transparency**: Added tooltips to the "Score" column showing granular breakdown (Location, Size, Age, etc.).
- **PDF Download**: Fully integrated `WeasyPrint` for high-fidelity PDF output via `POST /ui/download-pdf`.
- **Documentation**: Updated `README.md` with a clear "Demo Flow" section.

### Fixed
- **Analytics Handling**: Fixed server error in `_execute_search_flow` regarding Pydantic model assignment.
- **Constraints Display**: Fixed logic to display `total_found` and `was_capped` correctly in the UI.

### Verified
- **Tests**: `tests/test_ui_rendering.py` and `tests/test_pdf_download.py` passing.

---

## 2026-01-25: PDF Generation

### Added
- **PDF Rendering**: Implemented `renderer/pdf.py` using `WeasyPrint` to generate high-fidelity, printable CMA reports.
- **PDF Download Endpoint**: Added `POST /ui/download-pdf` to allow generating and downloading PDF reports directly from the UI.
- **Dependencies**: Added `weasyprint` (and its dependencies Pango/Cairo) to the environment.

### Verified
- **PDF Output**: Added `tests/test_pdf_download.py` confirming correct Content-Type (application/pdf), Content-Disposition headers, and valid PDF binary structure.

---

## 2026-01-25: Review UI & Standard Layout

### Added
- **Review UI**: Implemented `renderer/templates/review.html` allowing agents to:
  - View ranked candidates with explicit "Why this comp" reasons.
  - Review score breakdowns (e.g., "95% match").
  - Toggle candidates for inclusion/exclusion.
  - Modify search assumptions (Radius, Max Age) and re-run search.
- **Base Template**: Created `renderer/templates/base.html` to enforce consistent branding and sticky disclaimer footers.
- **Disclaimer System**: Added hardcoded "Informational only; not an appraisal" banner to every page footer and report header `renderer/templates/ui_report.html`.

### Changed
- **UI Routes**: Updated `app/main.py` with `POST /ui/search`, `/ui/update-criteria`, and `/ui/generate` to power the full interactive workflow.
- **Template Inheritance**: Refactored `index.html` and `ui_report.html` to extend `base.html`, ensuring standardized layout.

### Verified
- **Rendering**: Added `tests/test_ui_rendering.py` confirming disclaimer presence and correct template composition on all screens.

---

## 2026-01-25: Deterministic Ranking & Review Workflow

### Added
- **Human-in-the-Loop Review**: Implemented `ReviewPacket` and API workflow (`/search-comps` returns ranked candidates -> `/select-comps` -> `/generate-report`).
- **Deterministic Ranking**: `analytics/ranking.py` now uses weighted multi-factor scoring (location, size, rooms, age, recency) instead of opaque similarity.
- **Selection Reasons**: Ranking engine generates explicit, fact-based bullet points (e.g., "Exact bedroom match", "Recent sale") for every candidate.
- **Provenance Tracking**: `CompProperty` schema now tracks `data_source`, `data_timestamp`, and `score_breakdown`.
- **Review Events**: Added `REVIEW_STARTED`, `ASSUMPTIONS_MODIFIED`, and `REVIEW_COMPLETED` to audit log.

### Changed
- **API Response**: `POST /search-comps` now returns a `ReviewPacket` containing the ranked `candidates` list and `analytics_preview`, enabling the frontend to build a review screen.
- **Ranking Logic**: Replaced placeholder similarity scoring with `calculate_similarity_score` returning granular `ScoreBreakdown`.
- **Documentation**: Consolidated `next.md` and `NEXT.md` into a single canonical roadmap.

### Fixed
- **Candidate Ordering**: Comps are now strictly ordered by their calculated similarity score.

### Tests
- **New Verification**: Added `tests/test_api_review_workflow.py` to verify the full modify-review-generate cycle.
- **Passing**: 59/59 passing (including new API workflow tests).

---

## 2026-01-25: Web UI and Runtime Fixes

### Added
- **Notes-only Web UI**: 
  - `GET /ui`: Interactive form for pasting agent notes.
  - `POST /ui/generate`: Full pipeline execution (parse, search, select, report) with HTML preview.
  - `GET /ui/sample`: Sample notes retrieval.
- **Service Endpoints**:
  - `GET /`: Root endpoint with service metadata.
  - `GET /health`: Simplified health check returning `{"status": "ok"}`.

### Changed
- `app/main.py`: Configured `Jinja2Templates`, added UI routes and updated health check.
- `requirements.txt`: Added `python-multipart` for form data support.

### Fixed
- **Dataclass Runtime Error**: Reordered fields in `ProvenanceRecord` (`audit/provenance.py`) to ensure non-default arguments follow default arguments, resolving the uvicorn startup failure on Python 3.12.
- **Address Validation Loop**: Fixed critical validation errors where City-only inputs caused crashes. Relaxed `IntentIR` and `AddressInfo` schemas to accept empty strings for street/zip.
- **Mock Data Type Error**: Fixed runtime crash where integer zip codes from mock CSVs caused Pydantic validation failures. Added explicit type casting in `app/main.py`.
- **Hallucination False Positives**: Updated `allowed_values` logic to whitelist numeric zip codes and transaction years, preventing valid reports from being rejected as hallucinations.

---

## 2026-01-25: LLM Provider Switching System

### Added
- **Task-based model selection**: Different models for `notes` and `report` tasks
- **Per-task provider override**: Can use Ollama for notes, Claude for reports
- **Environment variable configuration**:
  - `LLM_PROVIDER`: "ollama" (default) or "claude"
  - `OLLAMA_BASE_URL`: default "http://localhost:11434"
  - `OLLAMA_MODEL`: default fallback model (default "llama3.2:latest")
  - `LLM_NOTES_MODEL`: optional override for notes task
  - `LLM_REPORT_MODEL`: optional override for report task
  - `ANTHROPIC_API_KEY`: required if LLM_PROVIDER=claude
  - `CLAUDE_MODEL`: default Claude model (default "claude-sonnet-4-20250514")
  - `CLAUDE_NOTES_MODEL`: optional override for notes task
  - `CLAUDE_REPORT_MODEL`: optional override for report task
  - `LLM_NOTES_PROVIDER`: optional per-task provider override
  - `LLM_REPORT_PROVIDER`: optional per-task provider override

### Changed
- `llm/client.py`: Added ClaudeClient, task-aware model selection, `get_client_for_task()` factory
- `app/settings.py`: Added new LLM environment variables with Ollama as default
- `llm/notes_parser.py`: Now passes `task="notes"` for model selection
- `llm/report_writer.py`: Now passes `task="report"` for model selection
- OllamaClient now uses `/api/chat` endpoint for better prompt handling

### Recommended Development Models
- Notes parsing: `llama3.2:latest` (2GB, fast)
- Report writing: `llama3.1:latest` (4.9GB, better quality)

### Fixed
- Date/datetime type mismatch in `connectors/reso_mock_connector.py` - added `_normalize_for_comparison()` helper
- End-to-end test no longer triggers false positive hallucination detection

### Test Status
**57/57 passing** ✅

---

## 2026-01-24: Initial Implementation

### Added
- Complete CMA compiler with domain models, connectors, LLM layer
- IntentIR, QueryPlan, ReportJSON schemas with Pydantic v2
- Anti-hallucination system with numeric verification
- Audit logging and provenance tracking
- HTML report renderer with Jinja2
- FastAPI application with 4 endpoints
