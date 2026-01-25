# CMA Tool Roadmap

## Product Positioning
A fast, defensible CMA draft tool that reduces MLS UI friction while preserving compliance and trust.

## Product Reality Check
- **Tables First**: Real CMAs are table-heavy tools. Focus on the core data grid before the narrative.
- **Optional Prose**: Narrative sections are a value-add for client presentation, not the primary engine of trust.
- **Foundational Trust**: Prioritize credibility, familiarity (matching local MLS conventions), and defensibility over aesthetic polish.

## Minimum “Real Product” Checklist
The following must be present for a demo-ready MVP:
- **Recognizable Layout**: Standardized sections: Subject Property Summary -> Comparables Table -> Key Market Metrics.
- **Explicit Disclaimers**: Hardcoded "Informational only; not an appraisal" and "Based on data from [MLS Source]" visible on every page.
- **Defensible Logic**: Fact-based bullets for "Why these comps" (e.g., "Sold within 0.5 miles," "Matched bed/bath count exactly").
- **Transparent Constraints**: Clearly show search limits (e.g., "Only showing top 5/20 matches") and data vintage.
- **Editable Logic assumptions**: Allow the agent to adjust core filters like SqFt tolerance (%) or search radius directly from the UI.

## Data Strategy
- **Analogous Mocking**: The current CSV + `reso_mock_connector` is intentionally designed to mirror real RESO Web API constraints. 
- **Market Sensitivity**: Add a second mock dataset (e.g., San Francisco or a high-density urban market) to test the parser against varying density/price/lot-size conventions.
- **Swappable Plugs**: Real MLS integration should be a "zero logic" swap of the connector implementation, keeping the domain logic untouched.

## Model Strategy
- **Parsing Focus**: Use local Ollama or cheap hosted LLMs (3.2B / 7B class) for the initial IntentIR extraction. Claude-tier models are overkill here.
- **Optional Narrative**: Higher-quality models should only be invoked for the optional narrative section, and only if the agent requests it.
- **Determinism First**: Favor schema-enforced Pydantic validation and strict "anti-hallucination" checks over agentic creativity.

## Strategic Roadmap (Reorganized)

### Phase 2: Connectivity & Location (Real-World Readiness)
- [ ] **Connect Real RESO API**: Replace mock connector with `connectors/reso_real_connector.py`.
- [ ] **Credential Management**: Securely handle MLS OIDC tokens.
- [ ] **Geocoding**: Add Google Maps/Mapbox integration for real distance calculations.

### Phase 3: Analytics & Accuracy
- [ ] **Improved Comp Ranking**: Replace simple similarity score with weighted multi-factor model (location, condition, recency).
- [ ] **Adjustment Logic**: Implement paired-sales analysis for data-driven price adjustments ($ per bed, $ per sqft).
- [ ] **PDF Export**: Generate professional, "printable" PDF reports for agents to share.

### Phase 4: Distribution & Deployment
- [ ] **User Authentication**: Implement basic login/signup for agent sessions.
- [ ] **Email Integration**: Email reports directly to agents.
- [ ] **Deployment**: Dockerize for cloud hosting (AWS/GCP).

## What NOT to do next (Future-Me Warning)
- **❌ UI Over-Polish**: Do not waste time on complex animations or bespoke CSS components until the data defensibility is proven.
- **❌ Long Prose**: Do not try to make the AI write "essays." Keep narrative sections to 1-2 factual paragraphs.
- **❌ Replace the MLS**: This is a draft tool to *assist* agents, not a replacement for their MLS login or professional judgment.
- **❌ Premature Visuals**: Do not add charts, maps, or price trend graphs until the underlying adjustment math is vetted by a human agent.
- **❌ "AI-Powered" Hype**: Avoid marketing this as "generative magic." It is a structured data tool with an LLM interface.
