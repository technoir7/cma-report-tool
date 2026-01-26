# CMA Compiler Roadmap (Canonical)

## Done
- [x] **Fix WeasyPrint/pydyf conflict**: Pinned `pydyf < 0.12` to restore PDF rendering for WeasyPrint 62.1.

## Follow-ups
- [ ] **Upgrade WeasyPrint**: Upgrade to `weasyprint >= 63` to remove the `pydyf` version pin.

## Snapshot
Backend-complete MVP with deterministic ranking, agent-reviewable "Review Packets", and immutable audit logs. Strict separation of stochastic LLM (Intent/Narrative) and deterministic Logic (Ranking/Math).

## Product Positioning
A fast, defensible CMA draft tool that reduces MLS UI friction while preserving compliance and trust.

## Product Reality Check
- **Tables First**: Real CMAs are table-heavy tools. Focus on the core data grid before the narrative.
- **Optional Prose**: Narrative sections are a value-add for client presentation, not the primary engine of trust.
- **Foundational Trust**: Prioritize credibility, familiarity (matching local MLS conventions), and defensibility over aesthetic polish.

## Current State (Verified)
- **Core Pipeline**: Functional and tested (59/59 passing tests).
- **Domain Layer**:
  - Strongly typed schemas acting as firewalls (`IntentIR`, `QueryPlan`, `ReportJSON`, `ReviewPacket`).
  - `CompProperty` includes strict provenance (`data_source`, `timestamp`) and explicit `selection_reasons`.
- **Analytics Engine**:
  - Deterministic ranking module (`analytics/ranking.py`) with weighted multi-factor scoring (location, size, rooms, age, recency).
  - Explicit reason generation (e.g., "Exact bedroom match").
- **Review Workflow**:
  - `ReviewPacket` API flow implemented (`/search-comps` -> `ReviewPacket` -> `/select-comps` -> `/generate-report`).
  - **Human-in-the-Loop UI**: Web interface (`/ui`) allows agents to review candidates, see explicit ranking reasons, and toggle inclusions before generation.
  - Supports "Human-in-the-Loop" review of candidates and assumptions.
- **LLM Layer**:
  - Task-based switching (Ollama/Claude) for "Notes" vs "Report".
  - **Constraint**: LLMs never access data directly and cannot invent numeric values.
- **Safety**:
  - `audit/`: Immutable logs with new Review events (`REVIEW_STARTED`, `ASSUMPTIONS_MODIFIED`, `REVIEW_COMPLETED`).
  - `HallucinationVerifier`: Numeric verification of generated narrative.
- **Output**:
  - **HTML**: Standardized layouts (`base.html`) with interactive review.
  - **PDF**: Professional PDF generation via `WeasyPrint` (endpoint `/ui/download-pdf`).
- **Connectors**:
  - Implemented: `RESOmockConnector`, `CSVConnector`.
  - Stubbed: `RESORealConnector`.
- **Developer Experience**:
  - Single-command dev runner implemented: `./scripts/dev.sh` (handles environment and startup).

## Minimum “Real Product” Checklist
The following must be present for a demo-ready MVP:
- [x] **Defensible Logic**: Fact-based bullets for "Why these comps" (Implemented in `ranking.py`).
- [x] **Editable Logic assumptions**: API supports modifying IntentIR in `ReviewPacket` (UI pending).
- [x] **Recognizable Layout**: Standardized sections (Subject -> Comps -> Metrics) via `base.html` + `report.html`.
- [x] **Explicit Disclaimers**: Hardcoded "Informational only; not an appraisal" visible on every page.
- [x] **Transparent Constraints**: Clearly show search limits (e.g., "Only showing top 5/20 matches").
- [x] **One-Command Demo**: Simplified startup via `./scripts/dev.sh`.
- [x] **Smart Defaults**: "Older home" queries don't trigger strict filters; `session_id` is auto-generated if missing.


## Near-Term Roadmap (Next 1–3 milestones)

### 1. Data Integration (High Priority)
- [ ] **Implement Real RESO Connector**: The logical interface exists (`connectors/reso_real_connector.py`), but requires:
  - OAuth2 implementation.
  - Rate limiting logic.
  - Field mapping from production RESO dictionaries.

### 2. Output Generation
- [x] **PDF Rendering**: Implemented using `WeasyPrint` via `renderer/pdf.py`.
- [ ] **Advanced Templates**: Expand HTML/Jinja2 templates to support agency branding.

### 3. Production Hardening
- [ ] **Authentication**: Add user auth to the API.
- [ ] **Persistent Storage**: Move audit logs from file/memory to a database (Postgres).
- [ ] **Deployment**: Dockerize for cloud deployment with secret management.

### 4. Production Hardening
- [ ] **Authentication**: Add user auth to the API.
- [ ] **Persistent Storage**: Move audit logs from file/memory to a database (Postgres).
- [ ] **Deployment**: Dockerize for cloud deployment with secret management.

## Strategic Roadmap (Phases)

### Phase 2: Connectivity & Location (Real-World Readiness)
- [ ] **Connect Real RESO API**: Replace mock connector.
- [ ] **Credential Management**: Securely handle MLS OIDC tokens.
- [ ] **Geocoding**: Add Google Maps/Mapbox integration for real distance calculations.

### Phase 3: Analytics & Accuracy
- [x] **Improved Comp Ranking**: Weighted multi-factor model implemented.
- [ ] **Adjustment Logic**: Implement paired-sales analysis ($ per bed, $ per sqft).
- [ ] **PDF Export**: Generate professional "printable" reports.

### Phase 4: Distribution & Deployment
- [ ] **User Authentication**: Implement basic login/signup.
- [ ] **Email Integration**: Email reports directly.

## Model Strategy
- **Task-Based Switching**:
  - *Notes Task*: `llama3.2:latest` (Fast, low VRAM).
  - *Report Task*: `Claude (Sonnet)` (Superior narrative).
  - Infrastructure supports per-task provider overrides via environment variables.
- **Determinism First**: Favor schema-enforced Pydantic validation over agentic creativity.
- **Parsing Focus**: Use cheap models for IntentIR extraction.

## Data Strategy
- **Analogous Mocking**: Current `reso_mock_connector` mirrors real RESO constraints.
- **Market Sensitivity**: Add a second mock dataset (e.g., high-density) to test parser.
- **Swappable Plugs**: Real MLS integration is a "zero logic" swap keeping domain logic untouched.

## What NOT to do next (Future-Me Warning)
- **❌ UI Over-Polish**: Do not waste time on complex animations until data defensibility is proven.
- **❌ Long Prose**: Keep narrative sections to 1-2 factual paragraphs.
- **❌ Replace the MLS**: This is a draft tool to *assist* agents.
- **❌ Premature Visuals**: No charts/maps until adjustment math is vetted.
- **❌ "AI-Powered" Hype**: It is a structured data tool with an LLM interface.

## Open Questions / Risks
- **Connectors**: RESO OIDC complexity is often underestimated.
- **Geocoding**: Need a strategy for lat/long lookup if MLS doesn't provide it reliably.
