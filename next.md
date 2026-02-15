# CMA Report Tool - Production Architecture Roadmap

## Context

**Current System:**
- **Pipeline**: FastAPI stateless pipeline with synchronous endpoints.
- **State**: In-memory `AppState.sessions` (dict), `AuditLog`, and `ProvenanceTracker`.
- **Core**: Deterministic ranking and analytics; LLM isolated to Notes->IntentIR and Data->Narrative.
- **Verification**: `HallucinationVerifier` checks numeric claims.
- **Data**: CSV + RESO Mock implemented; `RESORealConnector` is a stub.
- **Output**: PDF generation is synchronous.

---

## 1. Traceability & Versioning

**Goal:** Complete observability from request to report.

*   **Global Run ID**: Every request (`/ui/search`) generates a unique `run_id` (UUID) at one-time initialization.
*   **Version Tags**: Log the following versions with every Run ID:
    *   `rules_version` (Ranking/Filtering logic)
    *   `prompt_version` (LLM templates)
    *   `connector_version` (Adapter logic)
    *   `analytics_version` (Math/Adjustment rules)
*   **Propagation**: `run_id` must be attached to every Audit entry, Provenance record, and Log line.

---

## 2. Persistence Layer Upgrade

**Goal:** Remove in-memory state to support restarts and horizontal scaling.

### Phase 1: Fastest Path (Redis)
*   **Storage**: Redis for Session state.
*   **Serialization**: Pydantic `model_dump_json()` for `IntentIR`, `ReviewPacket`, `Selection`.
*   **TTL**: Configurable (e.g., 24 hours).
*   **Audit**: Write audit logs to disk (JSONL) with log rotation.

### Phase 2: Production Path (Postgres)
*   **Storage**: Relational DB for strict schema enforcement.
*   **Schema Outline**:
    ```sql
    runs (
        run_id UUID PRIMARY KEY,
        created_at TIMESTAMPTZ,
        versions JSONB -- {rules: "1.0", prompt: "2.1", ...}
    )
    sessions (
        session_id UUID PRIMARY KEY,
        current_run_id UUID REFERENCES runs,
        state JSONB
    )
    artifacts (
        id UUID PRIMARY KEY,
        run_id UUID REFERENCES runs,
        type VARCHAR, -- "intent_ir", "query_plan", "review_packet"
        content JSONB,
        hash VARCHAR
    )
    reports (
        id UUID PRIMARY KEY,
        run_id UUID REFERENCES runs,
        final_pdf_path VARCHAR,
        narrative_text TEXT
    )
    ```

---

## 3. Transaction History (Audit Log)

**Goal:** Move from "debugging log" to "immutable legal record".

*   **Immutability**: Append-only design.
*   **Scope**: Record *business events*, not code debugging.
*   **Event Types**:
    *   `PARSE`: Input Notes -> Output IntentIR (stores hashes).
    *   `BUILD_QUERY`: IntentIR -> QueryPlan.
    *   `FETCH_LISTINGS`: QueryPlan -> ListingRecords (store IDs only).
    *   `RANK`: Listings -> Scored Candidates (store version).
    *   `SELECT`: Candidates -> User Selection.
    *   `CALCULATE`: Selection -> Adjustment/Analytics.
    *   `GENERATE_NARRATIVE`: Analytics -> Narrative Draft.
    *   `VERIFY`: Draft -> Verified Narrative.
    *   `RENDER`: Final Report Generation.

---

## 4. Deterministic Core Guarantees

**Goal:** Identical inputs + Identical Code = Identical Output (Bit-for-bit).

*   **Ordering**: Eliminate all unordered dictionary iterations. Enforce strict sort keys for all list operations.
*   **Floating Point**: Centralize `Decimal` handling (rounding, precision) in a dedicated math module. No ad-hoc `float()` conversions.
*   **Randomness**: Explicitly forbid `random` module in Core Logic. Ranking ties must be broken deterministically (e.g., by `ListingId`).
*   **Versioning**: Analytics logic must be versioned. Changing a weight requires a version bump.

---

## 5. External Integration (RESO)

**Goal:** Establish first real data connectivity.

*   **Vertical Slice**: Implement a minimal, read-only path for `RESORealConnector`.
    *   **Auth**: OAuth2 Client Credentials flow.
    *   **Mapping**: Map raw OData response -> Canonical `ListingRecord` (ignore strict alignment for now, focus on data flow).
    *   **Validation**: Pydantic validation at the boundary.
    *   **Testing**: Store raw RESO payloads as fixtures; mock network interactions to ensure logic works without live credentials.
    *   **Provenance**: Store the specific OData query hash and result hash.

---

## 6. Logic Hardening (LLM)

**Goal:** Zero tolerance for hallucination or schema violation.

### Notes Parser
*   **Validation**: Strict Pydantic parsing.
*   **Repair**: Implement a single-retry "Auto-Repair" loop for malformed JSON.
*   **Explicit Nulls**: Prompt engineering to force `null` for missing fields instead of guessing (e.g., "unknown" vs `null`).

### Narrative Writer
*   **Fact Bundling**: Pass *only* the specific facts (Subject Address, Price, Adj Value) to the context. Do *not* pass raw listings.
*   **Fail Closed**: If verification fails X times, return a "Structured Data Only" report (no narrative) rather than a hallucinated one.
*   **Expanded Verification**: Extend `HallucinationVerifier` to check qualitative claims (e.g., "subject has larger lot") against Data rules.

---

## 7. Output Scaling (PDF)

**Goal:** Prevent long-running PDF generation from blocking HTTP workers.

*   **Decision**: Move PDF generation to background job.
    1.  User clicks "Download PDF".
    2.  Server returns `job_id` (202 Accepted).
    3.  Worker generates PDF and stores to blob storage/disk.
    4.  Client polls `GET /jobs/{job_id}` -> 303 See Other (Download URL).
*   **Caching**: Cache generated PDFs by `run_id` + `content_hash`.

---

## 8. Reproducibility Bundle

**Goal:** "Time Travel" debugging and audit.

*   **Export**: Create a zip bundle containing:
    1.  `manifest.json` (Versions, Config, Run ID).
    2.  `intent_ir.json`
    3.  `query_plan.json`
    4.  `listings_snapshot.json` (The exact data used, needed if MLS changes later).
    5.  `audit_log.jsonl`
    6.  `final_report.json`
*   **Usage**: System must be able to "Replay" execution from a bundle to verify logic changes.
