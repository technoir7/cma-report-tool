# Project Status: CMA Compiler

## Overview
This project is a compliance-first real estate assistant that compiles unstructured user intent (realtor notes) into strict, verifiable comparative market analysis (CMA) reports. It acts as an "Intent Compiler" for the real estate domain, prioritizing accuracy and auditability over unchecked generative capabilities.

## Current State
The core pipeline is functional and tested (57/57 passing tests). The architecture enforces a strict separation between stochastic LLM operations and deterministic data retrieval.

### Core Components
- **Domain Layer** (`domain/`): Strongly typed schemas (`IntentIR`, `QueryPlan`, `ReportJSON`) act as firewalls between system components.
- **LLM Layer** (`llm/`): Handles "Notes → Intent" and "Data → Narrative" transformations.
  - **Constraint**: LLMs never access data directly and cannot invent numeric values.
- **Connectors** (`connectors/`): Abstraction layer for data sources.
  - Implemented: `RESOmockConnector`, `CSVConnector`.
  - Stubbed: `RESORealConnector`.
- **Safety**:
  - `audit/`: Immutable logs for compliance.
  - `HallucinationVerifier`: Numeric verification of generated narrative.

## Strategic Decisions

### LLM Strategy
We employ a **Task-Based Switching** strategy to balance cost/privacy during development and quality in production.

- **Development**: Local-first using Ollama.
  - *Notes Task*: `llama3.2:latest` (Fast, low VRAM).
  - *Report Task*: `llama3.1:latest` (Higher reasoning/coherence).
- **Production**:
  - *Report Task*: Targeted to use **Claude (Sonnet)** for superior narrative generation.
  - *Notes Task*: specialized smaller models or fine-tunes acceptable.
- **Infrastructure**: The `LLMClient` protocol supports per-task provider overrides via environment variables (`LLM_NOTES_PROVIDER`, `LLM_REPORT_PROVIDER`).

### Architecture & Branding
- **Repo Name**: `cma_compiler`. Intentionally domain-specific branding for the MVP.
- **Pattern**: While the underlying "Intent Compiler" pattern (Parsing → IR → Plan → Execute → Verify) is generalizable to other industries, we are focusing strictly on Real Estate vendors for the initial market entry.
- **Compliance First**: We sacrifice some flexibility for regulatory safety (e.g., Tier 2 data fields are hard-blocked from LLM contexts).

## Near-Term Roadmap

### 1. Data Integration (High Priority)
- **Implement Real RESO Connector**: The logical interface exists (`connectors/reso_real_connector.py`), but requires:
  - OAuth2 implementation.
  - Rate limiting logic.
  - Field mapping from production RESO dictionaries.

### 2. Output Generation
- **PDF Rendering**: `renderer/pdf.py` is currently a stub. Needs integration with `wkhtmltopdf` or `WeasyPrint` for printable reports.
- **Advanced Templates**: Expand HTML/Jinja2 templates to support agency branding requirements.

### 3. User Interface
- **Web Frontend**: Currently relies on API endpoints (`FastAPI`). Needs a simple React/Next.js interface for:
  - Inputting notes.
  - Reviewing/Selecting comps (human-in-the-loop step).
  - Viewing final reports.

### 4. Production Hardening
- **Authentication**: Add user auth to the API.
- **Persistent Storage**: Move audit logs from file/memory to a database (Postgres).
- **Deployment**: Dockerize for cloud deployment with secret management.

## Long-Term Evolution
1. **MVP**: Complete the Real Estate CMA tool and pilot with vendors.
2. **Expansion**: Identify other high-compliance domains (Legal discovery, Insurance claims) where the "Intent Compiler" pattern applies.
3. **Core Extraction**: Potentially refactor the core pipeline (Parser/Planner/Verifier) into a generic library, keeping the CMA logic as a plugin/configuration.
