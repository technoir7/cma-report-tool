# Future Development Plan

## Phase 2: Real Data Integration
- [ ] **Connect Real RESO API**: Replace mock connector with `connectors/reso_real_connector.py`.
- [ ] **Credential Management**: Securely handle MLS OIDC tokens.
- [ ] **Geocoding**: Add Google Maps/Mapbox integration for real distance calculations.

## Phase 3: Analytics & Quality
- [ ] **Improved Comp Ranking**: Replace simple similarity score with weighted multi-factor model (location, condition, recency).
- [ ] **Adjustment Logic**: Implement paired-sales analysis for data-driven price adjustments.
- [ ] **Charts & Visuals**: Add price trend graphs to the report.

## Phase 4: Production Readiness
- [ ] **User Authentication**: Implement login/signup (Auth0 or similar).
- [ ] **PDF Export**: Generate professional PDF reports for download.
- [ ] **Email Integration**: Email reports directly to agents.
- [ ] **Deployment**: Dockerize and deploy to cloud (AWS/GCP).
