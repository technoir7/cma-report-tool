# CMA Compiler History

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
